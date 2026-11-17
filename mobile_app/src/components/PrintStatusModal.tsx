import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { PrintJob } from '../types';
import { api } from '../services/api';

interface PrintStatusModalProps {
  visible: boolean;
  initialJob: PrintJob | null;
  billNo: string;
  onClose: () => void;
}

export const PrintStatusModal: React.FC<PrintStatusModalProps> = ({
  visible,
  initialJob,
  billNo,
  onClose,
}) => {
  const [job, setJob] = useState<PrintJob | null>(initialJob);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    setJob(initialJob);
  }, [initialJob]);

  useEffect(() => {
    if (!visible || !job || job.status === 'Printed') return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const updated = await api.getPrintJob(job.job_id);
        if (isMounted) {
          setJob(updated);
          if (updated.status === 'Printed' || updated.status === 'Print Failed') {
            clearInterval(interval);
          }
        }
      } catch (e) {
        // network polling failure, keep retrying
      }
    }, 1500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [visible, job?.job_id, job?.status]);

  if (!visible || !job) return null;

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const updated = await api.retryPrintJob(job.job_id);
      setJob(updated);
    } catch (e: any) {
      alert('Retry failed: ' + e.message);
    } finally {
      setRetrying(false);
    }
  };

  const isSuccess = job.status === 'Printed';
  const isFailed = job.status === 'Print Failed';
  const isPrinting = job.status === 'Printing' || job.status === 'Print Pending';

  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={styles.overlay}>
        <View style={styles.modalCard}>
          {/* Status Icon */}
          <View
            style={[
              styles.iconCircle,
              isSuccess && styles.iconSuccess,
              isFailed && styles.iconFailed,
              isPrinting && styles.iconPrinting,
            ]}
          >
            {isSuccess && <Text style={styles.iconSymbol}>✓</Text>}
            {isFailed && <Text style={styles.iconSymbol}>✕</Text>}
            {isPrinting && <ActivityIndicator color="#6d28d9" size="large" />}
          </View>

          {/* Title */}
          <Text style={styles.title}>
            {isSuccess && 'Receipt Printed!'}
            {isFailed && 'Print Failed'}
            {isPrinting && 'Sending to Counter Printer...'}
          </Text>

          {/* Description */}
          <Text style={styles.desc}>
            {isSuccess &&
              `Bill ${billNo} was successfully printed by the PC thermal service.`}
            {isFailed &&
              (job.error_message ||
                'Counter printer did not respond or PC Print Service is offline.')}
            {isPrinting &&
              `Spooling Bill ${billNo} wirelessly over shop Wi-Fi...`}
          </Text>

          {/* Meta Details */}
          <View style={styles.metaBox}>
            <View style={styles.metaRow}>
              <Text style={styles.metaLabel}>Job ID:</Text>
              <Text style={styles.metaVal}>{job.job_id}</Text>
            </View>
            <View style={styles.metaRow}>
              <Text style={styles.metaLabel}>Status:</Text>
              <Text
                style={[
                  styles.metaVal,
                  {
                    color: isSuccess
                      ? '#10b981'
                      : isFailed
                      ? '#ef4444'
                      : '#f59e0b',
                    fontWeight: '800',
                  },
                ]}
              >
                {job.status}
              </Text>
            </View>
            {job.attempts !== undefined && job.attempts > 0 && (
              <View style={styles.metaRow}>
                <Text style={styles.metaLabel}>Attempts:</Text>
                <Text style={styles.metaVal}>{job.attempts}</Text>
              </View>
            )}
          </View>

          {/* Action Buttons */}
          <View style={styles.btnRow}>
            {isFailed && (
              <TouchableOpacity
                style={[styles.btn, styles.retryBtn]}
                onPress={handleRetry}
                disabled={retrying}
              >
                {retrying ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.retryBtnText}>↻ Retry Print</Text>
                )}
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[
                styles.btn,
                isSuccess ? styles.doneBtn : styles.dismissBtn,
              ]}
              onPress={onClose}
            >
              <Text
                style={
                  isSuccess ? styles.doneBtnText : styles.dismissBtnText
                }
              >
                {isSuccess ? 'Done & Next Bill' : 'Close'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  modalCard: {
    width: '100%',
    maxWidth: 380,
    backgroundColor: '#ffffff',
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 15,
    shadowOffset: { width: 0, height: 6 },
  },
  iconCircle: {
    width: 68,
    height: 68,
    borderRadius: 34,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  iconSuccess: {
    backgroundColor: '#d1fae5',
  },
  iconFailed: {
    backgroundColor: '#fee2e2',
  },
  iconPrinting: {
    backgroundColor: '#ede9fe',
  },
  iconSymbol: {
    fontSize: 32,
    fontWeight: '900',
    color: '#059669',
  },
  title: {
    fontSize: 20,
    fontWeight: '800',
    color: '#111827',
    textAlign: 'center',
    marginBottom: 8,
  },
  desc: {
    fontSize: 13,
    color: '#6b7280',
    textAlign: 'center',
    lineHeight: 18,
    marginBottom: 16,
  },
  metaBox: {
    width: '100%',
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    padding: 12,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
  },
  metaLabel: {
    fontSize: 12,
    color: '#6b7280',
  },
  metaVal: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1f2937',
    fontFamily: 'monospace',
  },
  btnRow: {
    flexDirection: 'row',
    gap: 10,
    width: '100%',
  },
  btn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  doneBtn: {
    backgroundColor: '#6d28d9',
  },
  doneBtnText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '800',
  },
  retryBtn: {
    backgroundColor: '#dc2626',
  },
  retryBtnText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '800',
  },
  dismissBtn: {
    backgroundColor: '#f3f4f6',
  },
  dismissBtnText: {
    color: '#374151',
    fontSize: 14,
    fontWeight: '700',
  },
});
