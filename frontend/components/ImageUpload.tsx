// components/ImageUpload.tsx
import { useRef, useState } from "react";

interface Props {
  onUpload: (file: File) => void;
  loading: boolean;
}

export default function ImageUpload({ onUpload, loading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(file: File) {
    setPreview(URL.createObjectURL(file));
    onUpload(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div
      className={`upload-zone ${dragging ? "dragging" : ""} ${loading ? "loading" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !loading && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={handleChange}
        style={{ display: "none" }}
      />

      {preview ? (
        <div className="preview-container">
          <img src={preview} alt="Uploaded drawing" className="preview-image" />
          {loading && <div className="loading-overlay">Analyzing...</div>}
        </div>
      ) : (
        <div className="upload-prompt">
          <div className="upload-icon">📐</div>
          <p>Drag & drop a structural drawing here</p>
          <p className="upload-sub">or click to browse — PNG, JPEG, WebP</p>
        </div>
      )}
    </div>
  );
}
