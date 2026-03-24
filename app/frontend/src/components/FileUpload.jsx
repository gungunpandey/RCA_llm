import React, { useRef, useState } from 'react';

const MAX_FILES = 5;
const MAX_SIZE_MB = 10;
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf', 'video/mp4', 'video/quicktime'];

const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const fileIcon = (mime) => {
    if (mime.startsWith('image/')) return '🖼️';
    if (mime === 'application/pdf') return '📄';
    if (mime.startsWith('video/')) return '🎬';
    return '📎';
};

const FileUpload = ({ files, onChange }) => {
    const inputRef = useRef(null);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState('');

    const validate = (incoming) => {
        const combined = [...files, ...incoming];
        if (combined.length > MAX_FILES) {
            setError(`Max ${MAX_FILES} files allowed.`);
            return incoming.slice(0, MAX_FILES - files.length);
        }
        const oversized = incoming.filter(f => f.size > MAX_SIZE_MB * 1024 * 1024);
        if (oversized.length) {
            setError(`Some files exceed ${MAX_SIZE_MB} MB and were skipped.`);
            return incoming.filter(f => f.size <= MAX_SIZE_MB * 1024 * 1024);
        }
        const badType = incoming.filter(f => !ALLOWED_TYPES.includes(f.type));
        if (badType.length) {
            setError(`Unsupported file type(s) skipped.`);
            return incoming.filter(f => ALLOWED_TYPES.includes(f.type));
        }
        setError('');
        return incoming;
    };

    const addFiles = (newFiles) => {
        const arr = Array.from(newFiles);
        const valid = validate(arr);
        if (valid.length) onChange([...files, ...valid]);
    };

    const removeFile = (idx) => {
        const updated = files.filter((_, i) => i !== idx);
        onChange(updated);
        setError('');
    };

    const onDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        addFiles(e.dataTransfer.files);
    };

    return (
        <div className="fu-wrapper">
            {/* Drop zone */}
            <div
                className={`fu-dropzone ${dragOver ? 'fu-drag-over' : ''}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
            >
                <div className="fu-icon">📁</div>
                <p className="fu-hint">
                    <strong>Click or drag & drop</strong> files here
                </p>
                <p className="fu-sub">Images, PDF, Video — max {MAX_FILES} files · {MAX_SIZE_MB} MB each</p>
            </div>

            <input
                ref={inputRef}
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.mp4,.mov"
                style={{ display: 'none' }}
                onChange={(e) => addFiles(e.target.files)}
            />

            {error && <p className="fu-error">{error}</p>}

            {/* File list */}
            {files.length > 0 && (
                <ul className="fu-list">
                    {files.map((file, i) => (
                        <li key={`${file.name}-${i}`} className="fu-item">
                            <span className="fu-file-icon">{fileIcon(file.type)}</span>
                            <div className="fu-file-info">
                                <span className="fu-file-name">{file.name}</span>
                                <span className="fu-file-size">{formatBytes(file.size)}</span>
                            </div>
                            <button
                                type="button"
                                className="fu-remove"
                                onClick={() => removeFile(i)}
                                aria-label="Remove file"
                            >
                                ✕
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};

export default FileUpload;
