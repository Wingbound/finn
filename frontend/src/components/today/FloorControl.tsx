import { Segmented } from "@/components/States";
import type { Floor } from "@/lib/types";

export function FloorControl({ value, onChange }: { value: Floor; onChange: (f: Floor) => void }) {
  return (
    <Segmented<Floor>
      label="Show"
      options={[
        { value: "critical", label: "Critical" },
        { value: "important", label: "Important" },
        { value: "everything", label: "Everything" },
      ]}
      value={value}
      onChange={onChange}
    />
  );
}
