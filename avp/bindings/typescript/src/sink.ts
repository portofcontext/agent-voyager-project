/**
 * Trajectory event sinks.
 *
 * A `Sink` is where every emitted trajectory event leaves the agent; the
 * agent owns the run lifecycle, the sink owns serialization and I/O. Emission
 * is synchronous, matching the Rust `Sink`: one event serializes to one line.
 */
import { closeSync, openSync, writeSync } from "node:fs";

import type { Event } from "./index.js";

export interface Sink {
  emit(event: Event): void;
}

/** One event per line of NDJSON to stdout. */
export class StdioSink implements Sink {
  emit(event: Event): void {
    writeSync(1, JSON.stringify(event) + "\n");
  }
}

/**
 * One event per line of NDJSON to a file. The file is truncated on
 * construction, then each event is written in emission order, so a
 * concurrent reader (`tail -f`) sees progress. This satisfies the
 * `run --out <path>` contract; the Rust counterpart is `avp::sink::FileSink`.
 */
export class FileSink implements Sink {
  private fd: number | null;

  constructor(path: string) {
    this.fd = openSync(path, "w");
  }

  emit(event: Event): void {
    if (this.fd === null) throw new Error("FileSink is closed");
    writeSync(this.fd, JSON.stringify(event) + "\n");
  }

  close(): void {
    if (this.fd !== null) {
      closeSync(this.fd);
      this.fd = null;
    }
  }
}

/** Collects events in memory; useful in tests. */
export class MemorySink implements Sink {
  readonly events: Event[] = [];

  emit(event: Event): void {
    this.events.push(event);
  }
}
