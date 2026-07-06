import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { API_BASE } from "../lib/constants";

export default function DownloadLinks({ runId }) {
  return (
    <div className="download-row">
      <a
        className="download-btn"
        href={`${API_BASE}/runs/${runId}/memo`}
        target="_blank"
        rel="noreferrer"
        title="Download underwriting memo (PDF)"
      >
        <FileText size={16} />
        <Download size={11} className="download-badge" />
        <span>Memo</span>
      </a>
      <a
        className="download-btn"
        href={`${API_BASE}/runs/${runId}/cashflow`}
        target="_blank"
        rel="noreferrer"
        title="Download cash-flow summary (Excel)"
      >
        <FileSpreadsheet size={16} />
        <Download size={11} className="download-badge" />
        <span>Cash-flow</span>
      </a>
    </div>
  );
}
