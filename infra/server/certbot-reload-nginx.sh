#!/bin/sh
# Validate and reload Nginx after Certbot installs a renewed certificate.
set -eu

nginx -t
systemctl reload nginx.service
