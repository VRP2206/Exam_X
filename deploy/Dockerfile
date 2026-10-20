# ExamX web UI. Built and run by deploy/compose.yaml; see README "Deploying the website".
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY examx examx
COPY data data
# Run from /app rather than installing the package: examx finds data/ and output/ next to its source.
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
RUN useradd -u 1000 -m examx && mkdir -p output && chown examx output
USER examx
CMD ["python", "-m", "examx.cli", "serve", "--host", "127.0.0.1", "--port", "8014"]
