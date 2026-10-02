# Static assets served at the site root.
#
# Next.js expects this directory to exist, and web/Dockerfile's `runner` stage
# does `COPY --from=builder /app/public ./public`, so the production image build
# fails without it. Place favicon.ico, robots.txt or other root-served assets here.
