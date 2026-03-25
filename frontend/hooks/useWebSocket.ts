"use client";
import { useEffect, useRef, useCallback } from "react";
import type { BusEvent } from "@/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export function useWebSocket(onEvent: (event: BusEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_URL}/ws`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const event: BusEvent = JSON.parse(e.data);
        onEventRef.current(event);
      } catch {}
    };

    ws.onclose = () => {
      setTimeout(connect, 2000);
    };

    return ws;
  }, []);

  useEffect(() => {
    const ws = connect();
    return () => ws.close();
  }, [connect]);
}
