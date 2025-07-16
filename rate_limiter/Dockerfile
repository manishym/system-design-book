FROM golang:1.20-alpine

WORKDIR /app

COPY go.mod ./
COPY main.go ./

RUN go mod tidy
RUN go build -o rate-limiter

EXPOSE 8080

CMD ["./rate-limiter"]
