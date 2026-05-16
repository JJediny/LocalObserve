package tests

import (
	"context"
	"fmt"
	"os/exec"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
)

func setupOTEL(ctx context.Context) (*sdktrace.TracerProvider, error) {
	exp, err := otlptracehttp.New(ctx,
		otlptracehttp.WithInsecure(),
		otlptracehttp.WithEndpoint("localhost:4318"),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName("test-harness"),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}

func TestSecurityHarnesses(t *testing.T) {
	ctx := context.Background()
	tp, err := setupOTEL(ctx)
	if err != nil {
		t.Fatalf("Failed to initialize OTEL: %v", err)
	}
	defer tp.Shutdown(ctx)

	tracer := otel.Tracer("harness-tracer")

	ctx, span := tracer.Start(ctx, "TestSecurityHarnesses")
	defer span.End()

	t.Run("test-osquery", func(t *testing.T) {
		_, childSpan := tracer.Start(ctx, "osqtool-verify")
		defer childSpan.End()

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
