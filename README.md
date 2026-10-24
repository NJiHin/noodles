# Noodles

## Run with Docker

One image holds the app and the front end. Ollama (page transcription) runs on your own machine, so it can use your GPU.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [Ollama](https://ollama.com/download), then pull the model:

   ```
   ollama pull qwen3-vl:2b-instruct
   ```

2. Put the OpenAI key in a `.env` file in the repo root (never commit it):

   ```
   OPENAI_API_KEY=sk-...
   ```

3. Build and run:

   ```
   docker compose up --build
   ```

4. Open http://localhost:8000. Stop with Ctrl+C.

Courses, materials and run logs are kept in `data/` and `runs/` on your machine, not in the image.

To click through without a key or Ollama (fake models, no paid calls), add `NOODLES_FAKE=1` to `.env`.

On Linux, start Ollama with `OLLAMA_HOST=0.0.0.0` so the container can reach it.
