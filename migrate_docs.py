import os
import re
import glob

def clean_content(text):
    # Remove emojis
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Remove mentions of phases, status, etc.
    lines = text.split('\n')
    clean_lines = []
    skip_mode = False
    for line in lines:
        lower_line = line.lower()
        if re.match(r'^#+\s*(phase|status|current status|deployment status|next steps|resolved|resolution|update|action items).*', lower_line):
            skip_mode = True
            continue
        if skip_mode and re.match(r'^#+\s+', line):
            skip_mode = False
        if skip_mode:
            continue
        
        # strip emojis
        # just basic unicode filtering for typical emojis
        line = line.encode('ascii', 'ignore').decode('ascii')
        clean_lines.append(line)
        
    return '\n'.join(clean_lines)

topics = {
    'osquery.md': ['OSQUERY*.md', 'OSquery-linux-queries.md'],
    'deployment.md': ['DEPLOYMENT*.md', 'DEPLOYMENT*.txt', 'README_DEPLOYMENT.md'],
    'logs.md': ['LOG_*.md', 'HOST_LOG_*.md'],
    'quickstart.md': ['QUICKSTART*.md', 'START_HERE.md', 'README.md'],
    'benchmarks.md': ['BENCHMARK*.md'],
    'cisa-kev.md': ['CISA*.md'],
    'troubleshooting.md': ['DATASOURCE_FIX.md', 'ISSUE_RESOLVED.txt', 'EXPLAINER.md', '*TROUBLESHOOTING.md'],
    'optimization.md': ['DISK_OPTIMIZATION.md', 'STACK_EVAL_NOTES.md'],
    'commands.md': ['COMMANDS_REFERENCE.md'],
    'index.md': ['INDEX.md', 'DOCUMENTATION_INDEX.md', 'FINAL_*.md', 'PROJECT_PLAN.md', 'SETUP_SUMMARY.txt']
}

for topic, patterns in topics.items():
    topic_content = []
    files_to_remove = []
    for pattern in patterns:
        for file in glob.glob(pattern):
            if file == 'README.md' and topic != 'quickstart.md': continue
            if file == 'SECURITY.md' or file == 'CONTRIBUTING.md': continue
            with open(file, 'r') as f:
                content = clean_content(f.read())
                topic_content.append(f"## {file}\n\n" + content)
            files_to_remove.append(file)
            
    if topic_content:
        with open(f"docs/{topic}", 'w') as f:
            f.write('\n\n'.join(topic_content))
            
    # delete old files
    for file in files_to_remove:
        try:
            os.remove(file)
        except OSError:
            pass

print("Migration completed.")
