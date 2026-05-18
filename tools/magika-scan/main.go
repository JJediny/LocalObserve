package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/fs"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type CacheEntry struct {
	Mtime int64  `json:"mtime"`
	Size  int64  `json:"size"`
	Type  string `json:"type"`
	Score float64 `json:"score"`
}

type ScanCache struct {
	Entries map[string]CacheEntry `json:"entries"`
	mu      sync.RWMutex
}

func loadCache(path string) *ScanCache {
	cache := &ScanCache{Entries: make(map[string]CacheEntry)}
	data, err := os.ReadFile(path)
	if err == nil {
		json.Unmarshal(data, &cache.Entries)
	}
	return cache
}

func (c *ScanCache) save(path string) error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	data, err := json.MarshalIndent(c.Entries, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

type MagikaResult struct {
	Path   string `json:"path"`
	Result struct {
		Value struct {
			Output struct {
				Label string `json:"label"`
			} `json:"output"`
			Score float64 `json:"score"`
		} `json:"value"`
	} `json:"result"`
}

func main() {
	dir := flag.String("dir", "/home", "Directory to scan")
	cachePath := flag.String("cache", ".magika-cache.json", "Path to cache file")
	batchSize := flag.Int("batch", 50, "Number of files per docker call")
	flag.Parse()

	cache := loadCache(*cachePath)
	startTime := time.Now()
	
	var dirtyFiles []string
	var mu sync.Mutex

	fmt.Printf("Walking %s...\n", *dir)
	err := filepath.WalkDir(*dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			return nil
		}

		mtime := info.ModTime().Unix()
		size := info.Size()

		cache.mu.RLock()
		entry, exists := cache.Entries[path]
		cache.mu.RUnlock()

		if !exists || entry.Mtime != mtime || entry.Size != size {
			mu.Lock()
			dirtyFiles = append(dirtyFiles, path)
			mu.Unlock()
		}
		return nil
	})

	if err != nil {
		log.Printf("walk error: %v", err)
	}

	totalDirty := len(dirtyFiles)
	fmt.Printf("Found %d new/changed files to identify.\n", totalDirty)

	for i := 0; i < totalDirty; i += *batchSize {
		end := i + *batchSize
		if end > totalDirty {
			end = totalDirty
		}
		batch := dirtyFiles[i:end]
		
		fmt.Printf("Scanning batch %d-%d/%d...\n", i+1, end, totalDirty)
		
		// Map host paths to /host-root for Docker
		args := []string{"run", "--rm", "-v", "/:/host-root:ro", "magika", "--json"}
		for _, f := range batch {
			absPath, _ := filepath.Abs(f)
			args = append(args, filepath.Join("/host-root", absPath))
		}

		cmd := exec.Command("docker", args...)
		out, err := cmd.Output()
		if err != nil {
			log.Printf("docker error on batch %d: %v (output: %s)", i, err, string(out))
			continue
		}

		var results []MagikaResult
		if err := json.Unmarshal(out, &results); err != nil {
			log.Printf("json error on batch %d: %v", i, err)
			continue
		}

		cache.mu.Lock()
		for _, res := range results {
			// Strip /host-root prefix back to original path
			origPath := res.Path[10:] // len("/host-root")
			
			info, _ := os.Stat(origPath)
			if info != nil {
				cache.Entries[origPath] = CacheEntry{
					Mtime: info.ModTime().Unix(),
					Size:  info.Size(),
					Type:  res.Result.Value.Output.Label,
					Score: res.Result.Value.Score,
				}
			}
		}
		cache.mu.Unlock()
		
		// Save incrementally
		cache.save(*cachePath)
	}

	fmt.Printf("\nScan complete in %v\n", time.Since(startTime))
	fmt.Printf("Identified: %d, Total in cache: %d\n", totalDirty, len(cache.Entries))
}
