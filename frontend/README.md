# Frontend — Multi-Agent Research Assistant

Next.js 16 chat interface for the research pipeline.

## Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout — nav bar, fonts, dark theme
│   │   ├── page.tsx            # Chat interface (main page)
│   │   ├── history/page.tsx    # Job history list
│   │   └── job/[id]/page.tsx   # Individual job detail view
│   ├── components/
│   │   ├── StatusBadge.tsx     # Status pill + pipeline stepper
│   │   ├── ScoreCard.tsx       # Evaluation score display
│   │   ├── ReportView.tsx      # Markdown report renderer
│   │   ├── ReasoningPanel.tsx  # Collapsible reasoning trace
│   │   └── MermaidDiagram.tsx  # Mermaid diagram renderer
│   ├── hooks/
│   │   └── useJobPoller.ts     # Polls GET /api/research/{id} until terminal
│   └── lib/
│       └── api.ts              # Typed API client
├── public/
├── package.json
└── tsconfig.json
```

## Pages

| Route | Description |
|---|---|
| `/` | Chat interface — submit questions, view live progress and reports |
| `/history` | List of all past research jobs with status and links |
| `/job/[id]` | Full detail view for a single job — report, scores, reasoning |

## Setup

```bash
npm install
```

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=your-api-key    # same value as API_KEY in the backend .env
```

If `NEXT_PUBLIC_API_KEY` is set, every request includes an `X-API-Key` header automatically. Leave it empty if the backend has auth disabled.

## Running

```bash
npm run dev      # development server — http://localhost:3000
npm run build    # production build
npm run start    # serve the production build
npm run lint     # ESLint check
```

## Stack

| | |
|---|---|
| Framework | Next.js 16.2 (App Router) |
| UI | React 19, Tailwind CSS 4, `@tailwindcss/typography` |
| Markdown | `react-markdown` |
| Diagrams | `mermaid` |
| Language | TypeScript 5 |
| Fonts | Geist Sans + Geist Mono (via `next/font`) |

## API client

`src/lib/api.ts` exports typed functions for every backend endpoint:

```ts
submitResearch(question)          // POST   /api/research
getJob(jobId)                     // GET    /api/research/{id}
getReasoning(jobId)               // GET    /api/research/{id}/reasoning
listJobs()                        // GET    /api/research
deleteJob(jobId)                  // DELETE /api/research/{id}
clearAllJobs()                    // DELETE /api/research
downloadPdf(jobId, question)      // GET    /api/research/{id}/pdf
checkHealth()                     // GET    /api/health
```

Polling is handled by `useJobPoller` (2 s interval, stops when status is `completed` or `failed`).

## Deployment

### Vercel / any Node host

```bash
npm run build
```

Set environment variables in your hosting dashboard:

```
NEXT_PUBLIC_API_URL=https://your-api-domain.com
NEXT_PUBLIC_API_KEY=your-production-api-key
```

The app is a standard Next.js project and deploys without configuration to Vercel, Netlify, or any Node-capable host.

### Docker

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

> Requires `output: "standalone"` in `next.config.js` for the slim image to work.

Build and run:

```bash
docker build -t research-frontend .
docker run -d \
  -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=https://your-api-domain.com \
  -e NEXT_PUBLIC_API_KEY=your-key \
  research-frontend
```

### nginx (reverse proxy)

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```
