// components/ResultTables.tsx
interface Corner {
  label: string;
  x: number;
  y: number;
}

interface Segment {
  number: number;
  end1: string;
  end2: string;
}

interface Props {
  corners: Corner[];
  segments: Segment[];
  unit: string;
}

export default function ResultTables({ corners, segments, unit }: Props) {
  return (
    <div className="tables">
      <div className="table-section">
        <h3>Point Table</h3>
        <table>
          <thead>
            <tr>
              <th>Point</th>
              <th>X ({unit})</th>
              <th>Y ({unit})</th>
            </tr>
          </thead>
          <tbody>
            {corners.map((c) => (
              <tr key={c.label}>
                <td>{c.label}</td>
                <td>{c.x}</td>
                <td>{c.y}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="table-section">
        <h3>Line Segment Table</h3>
        <table>
          <thead>
            <tr>
              <th>Segment</th>
              <th>End 1</th>
              <th>End 2</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((s) => (
              <tr key={s.number}>
                <td>{s.number}</td>
                <td>{s.end1}</td>
                <td>{s.end2}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
