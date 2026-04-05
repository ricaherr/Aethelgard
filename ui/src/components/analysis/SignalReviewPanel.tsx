import React from 'react';
import { CheckCircle2, Clock3, RefreshCw, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { PendingSignalReview } from '../../hooks/useSignalReviews';

interface SignalReviewPanelProps {
  pendingReviews: PendingSignalReview[];
  loading: boolean;
  onRefresh: () => Promise<void> | void;
  onApprove: (signalId: string) => Promise<void> | void;
  onReject: (signalId: string) => Promise<void> | void;
}

const formatRemaining = (seconds: number): string => {
  const safe = Math.max(0, seconds || 0);
  const mm = Math.floor(safe / 60);
  const ss = safe % 60;
  return `${mm.toString().padStart(2, '0')}:${ss.toString().padStart(2, '0')}`;
};

export const SignalReviewPanel: React.FC<SignalReviewPanelProps> = ({
  pendingReviews,
  loading,
  onRefresh,
  onApprove,
  onReject,
}) => {
  return (
    <div className="rounded-xl border border-aethelgard-gold/25 bg-aethelgard-gold/5 p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock3 size={16} className="text-aethelgard-gold" />
          <h3 className="text-[11px] font-black tracking-[0.2em] uppercase text-aethelgard-gold">
            Manual Review Queue
          </h3>
          <span className="text-[10px] text-white/60">{pendingReviews.length} pending</span>
        </div>
        <button
          onClick={() => onRefresh()}
          className="text-white/60 hover:text-white transition-colors"
          title="Refresh review queue"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {pendingReviews.length === 0 ? (
        <p className="text-[11px] text-white/50">No pending B/C-grade signals for review.</p>
      ) : (
        <div className="space-y-2 max-h-52 overflow-y-auto custom-scrollbar pr-1">
          {pendingReviews.map((review, idx) => (
            <motion.div
              key={review.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              className="rounded-lg border border-white/10 bg-white/[0.03] p-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-white">{review.symbol} {review.signal_type}</div>
                  <div className="text-[10px] text-white/60">
                    Reason: {review.trader_review_reason || 'B/C grade'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-white/40">Timeout</div>
                  <div className="text-xs font-mono text-aethelgard-gold">
                    {formatRemaining(review.remaining_seconds)}
                  </div>
                </div>
              </div>

              <div className="mt-2 flex items-center justify-between">
                <div className="text-[10px] text-white/50">
                  Conf: {(Number(review.confidence || 0) * 100).toFixed(0)}% | Price: {Number(review.price || 0).toFixed(5)}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onApprove(review.id)}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-bold bg-aethelgard-green/15 text-aethelgard-green border border-aethelgard-green/30 hover:bg-aethelgard-green/25 transition-colors"
                  >
                    <CheckCircle2 size={12} />
                    Approve
                  </button>
                  <button
                    onClick={() => onReject(review.id)}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-bold bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors"
                  >
                    <XCircle size={12} />
                    Reject
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
};
