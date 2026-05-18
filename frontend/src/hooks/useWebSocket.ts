"use client";

import { useEffect, useState, useRef, useCallback } from 'react';

export default function useWebSocket(url: string) {
    const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const retryCountRef = useRef(0);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('WebSocket connected');
            setIsConnected(true);
            retryCountRef.current = 0; // Reset retry counter on success
        };

        ws.onmessage = (event) => {
            setLastMessage(event);
        };

        ws.onclose = () => {
            setIsConnected(false);
            // Auto-reconnect with backoff: 1s, 2s, 4s, max 8s
            const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 8000);
            retryCountRef.current += 1;
            console.log(`WebSocket closed. Reconnecting in ${delay}ms...`);
            retryRef.current = setTimeout(connect, delay);
        };

        ws.onerror = () => {
            ws.close(); // triggers onclose → reconnect
        };
    }, [url]);

    useEffect(() => {
        connect();
        return () => {
            if (retryRef.current) clearTimeout(retryRef.current);
            wsRef.current?.close();
        };
    }, [connect]);

    return { lastMessage, isConnected };
}
