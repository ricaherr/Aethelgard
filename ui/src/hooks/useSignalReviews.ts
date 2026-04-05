import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApi } from './useApi';

interface SignalReviewPendingWsEvent {
  signal_id?: string;
  symbol?: string;
  event_type?: string;
}

export interface PendingSignalReview {
  id: string;
  symbol: string;
  signal_type: string;
  confidence: number;
  price: number;
  review_timeout_at: string;
  trader_review_reason: string;
  created_at: string;
  remaining_seconds: number;
  timeout_at: string;
  review_status: 'PENDING' | string;
}

interface ApproveResult {
  success: boolean;
  review?: { signal_id: string; status: string; message: string };
  execution?: { success?: boolean; message?: string };
  detail?: string;
}

interface RejectResult {
  success: boolean;
  signal_id?: string;
  status?: string;
  message?: string;
  detail?: string;
}

export function useSignalReviews() {
  const { apiFetch } = useApi();
  const [pendingReviews, setPendingReviews] = useState<PendingSignalReview[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshPending = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/signals/reviews/pending');
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Pending reviews API ${res.status}: ${text}`);
      }
      const data = await res.json();
      const reviews = Array.isArray(data?.pending_reviews) ? data.pending_reviews : [];
      setPendingReviews(reviews);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unknown error loading pending reviews';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  const approveReview = useCallback(async (signalId: string, reason?: string): Promise<ApproveResult> => {
    try {
      const res = await apiFetch(`/api/signals/reviews/${signalId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason ?? 'Approved from Analysis UI' }),
      });
      const data = await res.json();
      await refreshPending();
      return data;
    } catch (e) {
      return {
        success: false,
        detail: e instanceof Error ? e.message : 'Unknown error approving review',
      };
    }
  }, [apiFetch, refreshPending]);

  const rejectReview = useCallback(async (signalId: string, reason?: string): Promise<RejectResult> => {
    try {
      const res = await apiFetch(`/api/signals/reviews/${signalId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason ?? 'Rejected from Analysis UI' }),
      });
      const data = await res.json();
      await refreshPending();
      return data;
    } catch (e) {
      return {
        success: false,
        detail: e instanceof Error ? e.message : 'Unknown error rejecting review',
      };
    }
  }, [apiFetch, refreshPending]);

  useEffect(() => {
    refreshPending();
  }, [refreshPending]);

  useEffect(() => {
    const onSignalReviewPending = (event: Event) => {
      const custom = event as CustomEvent<SignalReviewPendingWsEvent>;
      const payload = custom.detail || {};

      setPendingReviews((prev) => {
        const signalId = payload.signal_id;
        if (!signalId || prev.some((item) => item.id === signalId)) {
          return prev;
        }
        const optimistic: PendingSignalReview = {
          id: signalId,
          symbol: payload.symbol || 'UNKNOWN',
          signal_type: 'BUY',
          confidence: 0,
          price: 0,
          review_timeout_at: '',
          trader_review_reason: 'B/C grade pending review',
          created_at: new Date().toISOString(),
          remaining_seconds: 300,
          timeout_at: '',
          review_status: 'PENDING',
        };
        return [optimistic, ...prev];
      });

      // Sync authoritative values from API right after WS push notification.
      void refreshPending();
    };

    window.addEventListener('aethelgard:signal-review-pending', onSignalReviewPending as EventListener);
    return () => {
      window.removeEventListener('aethelgard:signal-review-pending', onSignalReviewPending as EventListener);
    };
  }, [refreshPending]);

  useEffect(() => {
    // Fallback sync in case a WS packet is dropped.
    const id = setInterval(() => {
      void refreshPending();
    }, 60000);
    return () => clearInterval(id);
  }, [refreshPending]);

  const pendingCount = useMemo(() => pendingReviews.length, [pendingReviews]);

  return {
    pendingReviews,
    pendingCount,
    loading,
    error,
    refreshPending,
    approveReview,
    rejectReview,
  };
}
