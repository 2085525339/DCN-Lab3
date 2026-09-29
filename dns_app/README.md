# DCN Lab 3 - Problem 2

This directory contains the three services required by the assignment:

- `AS`: authoritative DNS server over UDP port `53533`
- `FS`: Fibonacci server over HTTP port `9090`
- `US`: user-facing server over HTTP port `8080`

## Local run

Open three terminal windows from this directory:

```bash
python3 AS/server.py
python3 FS/app.py
python3 US/app.py
```

Register the Fibonacci server with the authoritative server:

```bash
curl -i -X PUT http://127.0.0.1:9090/register \
  -H 'Content-Type: application/json' \
  -d '{"hostname":"fibonacci.com","ip":"127.0.0.1","as_ip":"127.0.0.1","as_port":"53533"}'
```

The expected registration status is `201`.

Test FS directly:

```bash
curl -i 'http://127.0.0.1:9090/fibonacci?number=8'
```

Expected body:

```text
21
```

Test the complete US -> AS -> FS flow:

```bash
curl -i 'http://127.0.0.1:8080/fibonacci?hostname=fibonacci.com&fs_port=9090&number=8&as_ip=127.0.0.1&as_port=53533'
```

## Docker run

Create a shared network and build the images:

```bash
docker network create dcn-dns-network
docker build -t dcn-as ./AS
docker build -t dcn-fs ./FS
docker build -t dcn-us ./US
```

Run AS first, then FS and US:

```bash
docker run -d --name dcn-as --network dcn-dns-network -p 53533:53533/udp dcn-as
docker run -d --name dcn-fs --network dcn-dns-network -p 9090:9090 dcn-fs
docker run -d --name dcn-us --network dcn-dns-network -p 8080:8080 dcn-us
```

Get the internal container IP addresses before registering FS:

```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' dcn-as
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' dcn-fs
```

Use the returned internal IP addresses in the registration request and in the
US request. Do not use `127.0.0.1` to refer to another container.

## Assignment checklist

- Keep the exact directory names `US`, `FS`, and `AS`.
- Keep the required ports and message formats unchanged.
- Commit the final `dns_app` directory to GitHub.
- Zip the complete `dns_app` directory for Brightspace submission.

