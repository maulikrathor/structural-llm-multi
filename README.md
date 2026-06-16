# Structural Section Analyzer

A web application that analyzes 2D structural engineering drawings and extracts precise corner coordinates, line segments, and exports CAD-compatible files.

Upload any structural section drawing — I-beam, T-beam, C-channel, L-section, Z-section, HSS, or even a hand-drawn sketch — and get back a fully labeled coordinate diagram, point table, line segment table, Excel report, DXF file, and JSON output.

---

## Demo

**Input:** A photo or scan of any 2D structural section drawing (with dimensions labeled)

**Output:**
- Clean labeled structural diagram with corners marked A, B, C...
- Point table with X, Y coordinates (origin at bottom-left)
- Line segment table (segment number, End 1, End 2)
- Downloadable Excel (.xlsx), DXF (.dxf), and JSON (.json) files

---

## How It Works

No OpenCV. No pixel detection. No training data.

The system sends the image to **Google Gemini 2.5 Flash** (a vision LLM) with a carefully engineered system prompt. Gemini reads the dimension annotations semantically — exactly like a human engineer would — and computes all corner coordinates mathematically. The frontend then renders a clean labeled diagram purely from the returned coordinates using HTML Canvas.

```
User uploads image
       ↓
FastAPI backend receives image
       ↓
Image encoded as Base64 → sent to Gemini 2.5 Flash with system prompt
       ↓
Gemini identifies section type, reads dimensions, computes coordinates
Returns structured JSON (section type, corners, line segments)
       ↓
Backend generates Excel + DXF from JSON
Returns everything to frontend
       ↓
Frontend renders labeled diagram (Canvas) + tables + download buttons
```

---

## Supported Section Types

| Section | Corners |
|---|---|
| I-beam (I-section) | 12 |
| T-beam (T-section) | 8 |
| C-channel (C-section) | 8 |
| L-section (Angle) | 6 |
| Z-section | 8 |
| Hollow Rectangular Section (RHS/HSS) | 8 |
| Structural Plate / Flat Bar | 4 |

Works with:
- Clean CAD-style drawings
- Scanned hand-drawn sketches
- Colored/filled diagrams
- Any dimension annotation style (`h=30`, `tw=0.7`, `bf=8`, symbolic or numeric)
- Dimensions given once (symmetric) or separately for top/bottom flanges

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (TypeScript) |
| Backend | FastAPI (Python) |
| LLM | Google Gemini 2.5 Flash |
| Excel export | openpyxl |
| DXF export | ezdxf |
| Diagram rendering | HTML Canvas (no extra API call) |
| Backend hosting | Railway |
| Frontend hosting | Vercel |

---

## Project Structure

```
structural_llm/
├── backend/
│   ├── main.py              # FastAPI app — POST /api/analyze endpoint
│   ├── prompt.py            # System prompt (core intelligence)
│   ├── gemini_client.py     # Gemini API call + JSON parsing
│   ├── exporters.py         # Excel (.xlsx) and DXF file generation
│   └── requirements.txt
│
├── frontend/
│   ├── pages/
│   │   ├── index.tsx        # Main page: upload + results
│   │   └── _app.tsx         # Global CSS loader
│   ├── components/
│   │   ├── ImageUpload.tsx      # Drag-and-drop image upload
│   │   ├── ResultTables.tsx     # Point table + line segment table
│   │   └── AnnotatedCanvas.tsx  # Structural diagram drawn from coordinates
│   ├── styles/globals.css
│   ├── next.config.js
│   └── package.json
│
├── .gitignore
└── README.md
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Google AI Studio API key → [aistudio.google.com](https://aistudio.google.com)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:
```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

Test it directly:
```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@your_image.png"
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # runs on http://localhost:3000
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Open [http://localhost:3000](http://localhost:3000) and upload a structural drawing.

---

## Deployment

### Backend → Railway

1. Create a new project on [railway.app](https://railway.app) from this GitHub repo
2. Set **Root Directory** to `backend`
3. Set **Start Command** to `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   ```
   GEMINI_API_KEY=your_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```
5. Deploy → Railway gives you a URL like `https://structural-llm-production.up.railway.app`

### Frontend → Vercel

1. Import this GitHub repo on [vercel.com](https://vercel.com)
2. Set **Root Directory** to `frontend`
3. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://your-railway-url.up.railway.app
   ```
4. Deploy

---

## API Reference

### `POST /api/analyze`

**Request:** `multipart/form-data` with field `file` (PNG, JPEG, or WebP, max 10MB)

**Response:**
```json
{
  "analysis": {
    "section_type": "I-beam",
    "unit": "cm",
    "dimensions_read": {
      "overall_height": 9,
      "overall_width": 8,
      "top_flange_thickness": 1,
      "bottom_flange_thickness": 1,
      "web_thickness": 0.7
    },
    "corners": [
      { "label": "A", "x": 0, "y": 9 },
      { "label": "B", "x": 8, "y": 9 },
      "..."
    ],
    "line_segments": [
      { "number": 1, "end1": "A", "end2": "B" },
      "..."
    ],
    "warnings": []
  },
  "exports": {
    "excel_b64": "<base64 encoded .xlsx>",
    "dxf_b64": "<base64 encoded .dxf>"
  }
}
```

**Coordinate convention:**
- Origin `(0, 0)` at bottom-left corner of structure
- X increases rightward
- Y increases upward
- Corners labeled A, B, C... clockwise from top-left

### `GET /api/health`

Returns `{ "status": "ok" }` — use for uptime checks.

---

## Environment Variables

| Variable | Location | Description |
|---|---|---|
| `GEMINI_API_KEY` | backend `.env` | Google AI Studio API key |
| `GEMINI_MODEL` | backend `.env` | Gemini model string (`gemini-2.5-flash`) |
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | Full URL of the backend server |

---

## Design Decisions

**Why LLM instead of computer vision?**
The previous prototype used 2200+ lines of OpenCV code (Hough transforms, edge detection, graph algorithms) to detect corners from pixel data. It required manual tuning for every new image style and failed on hand-drawn inputs. Replacing it with a single well-engineered LLM prompt reduced the codebase by ~90%, works on all image styles including hand-drawn, and handles any dimension annotation convention without code changes.

**Why draw a fresh diagram instead of annotating the original image?**
Superimposing coordinates onto the original image requires knowing exactly where the structure is within the image in pixel space — which varies per image. Drawing a clean diagram from the coordinate math is simpler, always correct, and actually more useful to the user since the clean diagram is uncluttered by dimension lines and arrows.

**Why direct fetch to Railway instead of through Vercel?**
Vercel serverless functions have a hard 10-second timeout. Gemini 2.5 Flash can take 2–4 minutes on complex images. The frontend calls Railway directly using `NEXT_PUBLIC_API_URL`.

---

## Roadmap

- [ ] Multi-agent extension: structural analysis agent for cut lines, joint recommendations, centroid and moment of inertia calculations
- [ ] SpringBoot backend migration
- [ ] Compound/complex section support
- [ ] Batch processing (multiple images)
- [ ] Section comparison view

---

## License

MIT
