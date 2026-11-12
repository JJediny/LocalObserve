# syntax=docker/dockerfile:1

FROM golang:1.27.3-bookworm@sha256:dc0963f32053e4bc451d24d87e3892d42d01021b61f093e98eb95c0352bb84b0 AS build

ARG SNITCH_VERSION=v0.2.2
ENV CGO_ENABLED=0 \
    GOOS=linux

# Build a static binary so the runtime needs no libc, shell, or package manager.
RUN go install \
    -trimpath \
    -ldflags="-s -w -X github.com/karol-broda/snitch/cmd.Version=${SNITCH_VERSION#v}" \
    "github.com/karol-broda/snitch@${SNITCH_VERSION}"

FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab

COPY --from=build /go/bin/snitch /usr/local/bin/snitch

ENTRYPOINT ["/usr/local/bin/snitch"]
CMD ["watch", "--interval=5s"]
