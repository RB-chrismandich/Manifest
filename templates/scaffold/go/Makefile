.PHONY: build test lint fmt vet clean

# Build the project
build:
	go build -o bin/ ./...

# Run tests with coverage
test:
	go test -v -race -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out

# Run linter
lint:
	golangci-lint run ./...

# Format code
fmt:
	gofmt -s -w .
	goimports -w .

# Run go vet
vet:
	go vet ./...

# Clean build artifacts
clean:
	rm -rf bin/ coverage.out

# Run all checks (lint + test)
check: fmt vet lint test
