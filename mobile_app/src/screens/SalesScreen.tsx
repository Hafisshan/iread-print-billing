import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { BillRecord, SalesSummary } from '../types';
import { api } from '../services/api';

export const SalesScreen: React.FC = () => {
  const [data, setData] = useState<SalesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchSales = async () => {
    try {
      const res = await api.getSales();
      setData(res);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to fetch sales summary.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchSales();
  }, []);

  const onRefresh = () => {
    setRefreshing(true);
    fetchSales();
  };

  return (
    <View style={styles.container}>
      {/* Today Summary Banner */}
      <View style={styles.summaryCard}>
        <View style={styles.summaryItem}>
          <Text style={styles.summaryLabel}>TODAY'S TOTAL SALES</Text>
          <Text style={styles.summarySales}>
            ₹{(data?.today_sales || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </Text>
          <Text style={styles.summaryDate}>{data?.today_date || ''}</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.summaryItem}>
          <Text style={styles.summaryLabel}>BILLS GENERATED</Text>
          <Text style={styles.summaryCount}>{data?.today_bill_count || 0}</Text>
          <Text style={styles.summarySub}>Counter Bills</Text>
        </View>
      </View>

      {/* Recent Bills Title */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recent Bills</Text>
        <Text style={styles.sectionSub}>Latest transactions</Text>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color="#6d28d9" size="large" />
      ) : (
        <FlatList
          data={data?.bills || []}
          keyExtractor={(item) => item.id.toString()}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 24, gap: 10 }}
          ListEmptyComponent={
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>No recent bills found.</Text>
            </View>
          }
          renderItem={({ item }: { item: BillRecord }) => {
            const isPaid = item.payment_status === 'Paid';
            const isUnpaid = item.payment_status === 'Unpaid';
            return (
              <View style={styles.billCard}>
                <View style={styles.billTopRow}>
                  <View>
                    <Text style={styles.billNo}>{item.bill_no}</Text>
                    <Text style={styles.billCustomer}>
                      {item.customer || 'Walk-in Customer'}
                    </Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={styles.billAmount}>₹{item.total.toFixed(2)}</Text>
                    <View
                      style={[
                        styles.statusBadge,
                        isPaid && styles.statusPaid,
                        isUnpaid && styles.statusUnpaid,
                        !isPaid && !isUnpaid && styles.statusPartial,
                      ]}
                    >
                      <Text
                        style={[
                          styles.statusBadgeText,
                          {
                            color: isPaid ? '#065f46' : isUnpaid ? '#991b1b' : '#92400e',
                          },
                        ]}
                      >
                        {item.payment_status}
                      </Text>
                    </View>
                  </View>
                </View>

                <View style={styles.billBottomRow}>
                  <Text style={styles.billMeta}>
                    🕒 {item.created_at ? item.created_at.slice(0, 19).replace('T', ' ') : ''}
                  </Text>
                  <Text style={styles.billMeta}>
                    💳 {item.payment_method}
                  </Text>
                </View>
              </View>
            );
          }}
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  summaryCard: {
    margin: 16,
    backgroundColor: '#6d28d9',
    borderRadius: 16,
    padding: 20,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    elevation: 3,
    shadowColor: '#6d28d9',
    shadowOpacity: 0.3,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
  },
  summaryItem: {
    flex: 1,
  },
  divider: {
    width: 1,
    height: 48,
    backgroundColor: 'rgba(255,255,255,0.2)',
    marginHorizontal: 16,
  },
  summaryLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: '#e9d5ff',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  summarySales: {
    fontSize: 22,
    fontWeight: '900',
    color: '#ffffff',
  },
  summaryDate: {
    fontSize: 11,
    color: '#c4b5fd',
    marginTop: 2,
  },
  summaryCount: {
    fontSize: 22,
    fontWeight: '900',
    color: '#ffffff',
  },
  summarySub: {
    fontSize: 11,
    color: '#c4b5fd',
    marginTop: 2,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    paddingHorizontal: 18,
    marginBottom: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0f172a',
  },
  sectionSub: {
    fontSize: 12,
    color: '#64748b',
  },
  billCard: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  billTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  billNo: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0f172a',
  },
  billCustomer: {
    fontSize: 12,
    color: '#475569',
    marginTop: 2,
  },
  billAmount: {
    fontSize: 16,
    fontWeight: '900',
    color: '#0f172a',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    marginTop: 4,
  },
  statusPaid: {
    backgroundColor: '#ecfdf5',
    borderWidth: 1,
    borderColor: '#a7f3d0',
  },
  statusUnpaid: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
  },
  statusPartial: {
    backgroundColor: '#fffbeb',
    borderWidth: 1,
    borderColor: '#fde68a',
  },
  statusBadgeText: {
    fontSize: 10,
    fontWeight: '800',
  },
  billBottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  billMeta: {
    fontSize: 11,
    color: '#64748b',
  },
  emptyBox: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    color: '#94a3b8',
    fontSize: 14,
  },
});
