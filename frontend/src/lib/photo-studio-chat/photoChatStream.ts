export interface StreamPhotoMedia {
  id: string;
  assetId?: number;
  url: string;
  fileName?: string;
  type: "image" | "video";
  prompt?: string;
}

export interface StreamChatMessage {
  id: string;
  role: "user" | "assistant";
  type: "welcome" | "text" | "image" | "action-progress" | "action-complete" | "action-error";
  content: string;
  timestamp: Date;
  photos?: StreamPhotoMedia[];
  isLoading?: boolean;
}

export interface ParsedSsePayloads {
  buffer: string;
  events: any[];
}

export function parseSsePayloads(buffer: string, chunkText: string): ParsedSsePayloads {
  const combined = `${buffer || ""}${chunkText || ""}`;
  const rawEvents = combined.split(/\r?\n\r?\n/);
  const nextBuffer = rawEvents.pop() || "";
  const events = rawEvents.flatMap((rawEvent) => {
    const dataLines = rawEvent
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6));
    if (!dataLines.length) return [];
    try {
      return [JSON.parse(dataLines.join("\n"))];
    } catch {
      return [];
    }
  });
  return { buffer: nextBuffer, events };
}

export function upsertGeneratedPhoto<T extends { assetId?: number; url: string }>(list: T[], photo: T): T[] {
  const next = list.filter((item) => {
    if (photo.assetId && item.assetId) {
      return item.assetId !== photo.assetId;
    }
    return item.url !== photo.url;
  });
  return [photo, ...next];
}

export function applyStreamErrorToMessages<T extends StreamChatMessage>(
  messages: T[],
  params: {
    botAdded: boolean;
    botMsgId: string;
    errorText: string;
    now?: Date;
  },
): T[] {
  const { botAdded, botMsgId, errorText, now = new Date() } = params;
  if (!botAdded) {
    return [
      ...messages,
      {
        id: `stream-error-${now.getTime()}`,
        role: "assistant",
        type: "action-error",
        content: errorText,
        timestamp: now,
        isLoading: false,
      } as T,
    ];
  }

  return messages.map((message) => (
    message.id === botMsgId
      ? {
          ...message,
          type: "action-error",
          content: errorText,
          isLoading: false,
        }
      : message
  ));
}
