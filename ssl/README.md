# SSL Certificates

This directory contains SSL certificates for secure database connections.

## Required Files

- `supabase.crt`: Supabase SSL certificate
- `root.crt`: Root CA certificate

## Setup Instructions

1. Download the Supabase SSL certificate from your project dashboard
2. Place the certificate in this directory as `supabase.crt`
3. Download the root CA certificate if required
4. Ensure proper permissions (read-only for application user)

## Security Notes

- Never commit certificates to version control
- Keep backups of certificates in a secure location
- Rotate certificates according to security policy
- Monitor certificate expiration dates 