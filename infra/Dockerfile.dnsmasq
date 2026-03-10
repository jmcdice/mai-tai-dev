FROM alpine:latest
RUN apk add --no-cache dnsmasq
ENTRYPOINT ["dnsmasq", "--keep-in-foreground", "--conf-file=/etc/dnsmasq.conf"]
