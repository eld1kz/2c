import { toChatEvent, type ChatEvent } from "./events";

/** Incremental parser for `text/event-stream`: feed decoded chunks, get whole events back. */
export function createSseParser(onEvent: (event: ChatEvent) => void) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk.replace(/\r\n?/g, "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let name = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      const event = data.length ? toChatEvent(name, data.join("\n")) : null;
      if (event) onEvent(event);
    }
  };
}
