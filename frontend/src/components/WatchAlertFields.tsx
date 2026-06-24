"use client";

import { Input } from "./Input";

export function WatchAlertFields({
  targetPrice,
  onTargetPriceChange,
  notifyAnyDrop,
  onNotifyAnyDropChange,
  minDropDollars,
  onMinDropDollarsChange,
  minDropPercent,
  onMinDropPercentChange,
}: {
  targetPrice: string;
  onTargetPriceChange: (v: string) => void;
  notifyAnyDrop: boolean;
  onNotifyAnyDropChange: (v: boolean) => void;
  minDropDollars: string;
  onMinDropDollarsChange: (v: string) => void;
  minDropPercent: string;
  onMinDropPercentChange: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <Input
        label="Target price (optional)"
        type="text"
        placeholder="29.99"
        hint="Alert when price falls to or below this amount"
        value={targetPrice}
        onChange={(e) => onTargetPriceChange(e.target.value)}
      />
      <label className="flex items-center gap-2.5 font-data text-xs text-muted cursor-pointer">
        <input
          type="checkbox"
          checked={notifyAnyDrop}
          onChange={(e) => onNotifyAnyDropChange(e.target.checked)}
          className="size-4 rounded border-border accent-primary"
        />
        Notify on any price drop
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          label="Min drop ($)"
          type="text"
          placeholder="5.00"
          hint="Only alert if price drops by at least this amount"
          value={minDropDollars}
          onChange={(e) => onMinDropDollarsChange(e.target.value)}
        />
        <Input
          label="Min drop (%)"
          type="number"
          min={1}
          max={100}
          placeholder="10"
          hint="Only alert if discount increases by at least this %"
          value={minDropPercent}
          onChange={(e) => onMinDropPercentChange(e.target.value)}
        />
      </div>
    </div>
  );
}
