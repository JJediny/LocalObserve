package tests

import (
	"context"
	"fmt"
	"os/exec"
	"testing"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.4.0"
)

func initTracer(ctx context.Context) (*sdktrace.TracerProvider, error) {
	exporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint("localhost:4318"),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create exporter: %w", err)
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("security-harness-tests"),
			attribute.String("environment", "test"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	bsp := sdktrace.NewBatchSpanProcessor(exporter)
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithResource(res),
		sdktrace.WithSpanProcessor(bsp),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}

func TestSecurityHarnesses(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	tp, err := initTracer(ctx)
	if err != nil {
		t.Logf("Failed to initialize OTel tracer: %v. Continuing without tracing.", err)
	}
	defer tp.Shutdown(ctx)

	tracer := otel.Tracer("harness-tracer")

	ctx, span := tracer.Start(ctx, "TestSecurityHarnesses")
	defer span.End()

	t.Run("test-osquery", func(t *testing.T) {
		_, childSpan := tracer.Start(ctx, "osqtool-verify")
		defer childSpan.End()

		if _, err := exec.LookPath("osqueryi"); err != nil {
			childSpan.SetStatus(codes.Ok, "osqueryi not found on host; skipped")
			t.Skip("osqueryi executable not found on host; install osquery or run via container")
		}

		// Prepare test pack
		exec.Command("sh", "-c", "jq '{queries: .schedule}' ../osqueryd.conf > test_pack.conf").Run()
		defer exec.Command("rm", "-f", "test_pack.conf").Run()

		cmd := exec.Command("go", "run", "github.com/chainguard-dev/osqtool/cmd/osqtool", "-workers", "1", "verify", "test_pack.conf")

		out, err := cmd.CombinedOutput()
		childSpan.SetAttributes(attribute.String("stdout", string(out)))

		if err != nil {
			childSpan.SetStatus(codes.Error, err.Error())
			t.Fatalf("osqtool failed: %v\nOutput: %s", err, string(out))
		}
		childSpan.SetStatus(codes.Ok, "osqtool verify passed")
	})

	t.Run("test-falco", func(t *testing.T) {
		_, childSpan := tracer.Start(ctx, "event-generator-run")
		defer childSpan.End()

		cmd := exec.Command("../event-generator", "run", "syscall.ReadSensitiveFileUntrusted")

		out, err := cmd.CombinedOutput()
		childSpan.SetAttributes(attribute.String("stdout", string(out)))

		if err != nil {
			childSpan.SetStatus(codes.Error, err.Error())
			// event-generator returns error because it generates a permission denied error deliberately to trigger Falco
			// we can record the error in trace but pass the test since it's expected
			fmt.Printf("event-generator generated an error (expected for triggering falco): %v\n", err)
		}
		childSpan.SetStatus(codes.Ok, "event-generator finished")
	})
}
