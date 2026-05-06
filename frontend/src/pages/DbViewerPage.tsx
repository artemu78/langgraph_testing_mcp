import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

interface DbTableListResponse {
  tables: string[];
}

interface DbTableRowsResponse {
  table: string;
  count: number;
  rows: Record<string, unknown>[];
}

interface PurgeResponse {
  table: string;
  deleted_rows: number;
}

const API_BASE = 'http://localhost:8000';

function DbViewerPage() {
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [purging, setPurging] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const loadTables = async () => {
      setLoading(true);
      setError('');
      setMessage('');
      try {
        const response = await fetch(`${API_BASE}/db/tables`);
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const data = (await response.json()) as DbTableListResponse;
        setTables(data.tables);
        if (data.tables.length > 0) {
          setSelectedTable(data.tables[0]);
        }
      } catch (err) {
        setError(`Failed to load tables: ${String(err)}`);
      } finally {
        setLoading(false);
      }
    };
    void loadTables();
  }, []);

  useEffect(() => {
    if (!selectedTable) {
      setRows([]);
      return;
    }
    const loadRows = async () => {
      setLoading(true);
      setError('');
      setMessage('');
      try {
        const response = await fetch(`${API_BASE}/db/table/${encodeURIComponent(selectedTable)}`);
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const data = (await response.json()) as DbTableRowsResponse;
        setRows(data.rows);
      } catch (err) {
        setError(`Failed to load table rows: ${String(err)}`);
      } finally {
        setLoading(false);
      }
    };
    void loadRows();
  }, [selectedTable]);

  const columns = useMemo(() => {
    const keySet = new Set<string>();
    rows.forEach((row) => Object.keys(row).forEach((key) => keySet.add(key)));
    return [...keySet];
  }, [rows]);

  const renderCell = (value: unknown) => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">null</span>;
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (
        (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']'))
      ) {
        try {
          const parsed = JSON.parse(trimmed);
          return <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(parsed, null, 2)}</pre>;
        } catch {
          return <span>{value}</span>;
        }
      }
    }
    if (typeof value === 'object') {
      return <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>;
    }
    return <span>{String(value)}</span>;
  };

  const purgeSelectedTable = async () => {
    if (!selectedTable) {
      return;
    }
    if (!window.confirm(`Purge all rows from "${selectedTable}"?`)) {
      return;
    }
    setPurging(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/db/table/${encodeURIComponent(selectedTable)}/purge`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data = (await response.json()) as PurgeResponse;
      setRows([]);
      setMessage(`Purged ${data.deleted_rows} row(s) from ${data.table}.`);
    } catch (err) {
      setError(`Failed to purge table: ${String(err)}`);
    } finally {
      setPurging(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="space-y-3">
          <Link to="/" className="text-sm text-blue-700 hover:underline">
            ← Back to homepage
          </Link>
          <h1 className="text-3xl font-bold">SQLite Data Viewer</h1>
          <p className="text-gray-600">Pick a table, inspect rows, and purge when needed.</p>
        </header>

        <section className="bg-white border rounded-xl p-4 flex flex-wrap gap-3 items-center">
          <label className="text-sm font-medium" htmlFor="table-select">
            Table
          </label>
          <select
            id="table-select"
            value={selectedTable}
            onChange={(e) => setSelectedTable(e.target.value)}
            className="border rounded-lg px-3 py-2 min-w-64"
            disabled={loading || tables.length === 0}
          >
            {tables.length === 0 && <option value="">No tables found</option>}
            {tables.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </select>
          <button
            onClick={purgeSelectedTable}
            disabled={!selectedTable || purging || loading}
            className="bg-red-600 text-white px-4 py-2 rounded-lg disabled:opacity-50"
          >
            {purging ? 'Purging...' : 'Purge'}
          </button>
        </section>

        {error && <div className="bg-red-50 text-red-700 border border-red-200 rounded-lg p-3">{error}</div>}
        {message && <div className="bg-green-50 text-green-700 border border-green-200 rounded-lg p-3">{message}</div>}

        <section className="bg-white border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b text-sm text-gray-600">
            {loading ? 'Loading...' : `Rows: ${rows.length}`}
          </div>
          <div className="overflow-auto max-h-[70vh]">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-100 sticky top-0">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="text-left font-semibold px-3 py-2 border-b whitespace-nowrap">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="align-top">
                    {columns.map((column) => (
                      <td key={`${rowIndex}-${column}`} className="px-3 py-2 border-b whitespace-pre-wrap">
                        {renderCell(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
                {rows.length === 0 && !loading && (
                  <tr>
                    <td className="px-3 py-6 text-gray-500" colSpan={Math.max(columns.length, 1)}>
                      No rows to display.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

export default DbViewerPage;
