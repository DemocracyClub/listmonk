FROM listmonk/listmonk:latest
ADD config.toml .

ENV LISTMONK_app__address=0.0.0.0:8000
ENV PORT=8000

COPY static* ./static
CMD ["./listmonk", "--static-dir=./static"]
EXPOSE 8000
