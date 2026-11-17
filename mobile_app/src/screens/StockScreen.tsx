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
import { StockItem } from '../types';
import { api } from '../services/api';

export const StockScreen: React.FC = () => {
  const [items, setItems] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStock = async () => {
    try {
      const data = await api.getStock();
      setItems(data);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to fetch inventory stock.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStock();
  }, []);

  const onRefresh = () => {
    setRefreshing(true);
    fetchStock();
  };

  const lowStockCount = items.filter((i) => i.is_low_stock).length;

  return (
    <View style={styles.container}>
      {/* Overview Header */}
      <View style={styles.headerBox}>
        <View>
          <Text style={styles.headerTitle}>Paper &amp; Stock Inventory</Text>
          <Text style={styles.headerSub}>Counter Stock Status (Read-Only)</Text>
        </View>
        {lowStockCount > 0 && (
          <View style={styles.alertBadge}>
            <Text style={styles.alertText}>⚠️ {lowStockCount} Low Stock</Text>
          </View>
        )}
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color="#6d28d9" size="large" />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id.toString()}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          contentContainerStyle={{ padding: 14, gap: 10 }}
          ListEmptyComponent={
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>No inventory stock records available.</Text>
            </View>
          }
          renderItem={({ item }) => (
            <View style={[styles.stockCard, item.is_low_stock && styles.stockCardWarning]}>
              <View style={styles.cardHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemName}>{item.item_name}</Text>
                  <Text style={styles.itemCategory}>
                    {item.category} • {item.size_spec || 'Standard'}
                  </Text>
                </View>

                {item.is_low_stock ? (
                  <View style={styles.lowStockTag}>
                    <Text style={styles.lowStockTagText}>LOW STOCK</Text>
                  </View>
                ) : (
                  <View style={styles.inStockTag}>
                    <Text style={styles.inStockTagText}>IN STOCK</Text>
                  </View>
                )}
              </View>

              <View style={styles.cardStatsRow}>
                <View style={styles.statCol}>
                  <Text style={styles.statLabel}>Available Sheets</Text>
                  <Text
                    style={[
                      styles.statVal,
                      { color: item.is_low_stock ? '#dc2626' : '#059669' },
                    ]}
                  >
                    {item.available_sheets}
                  </Text>
                </View>

                <View style={styles.statCol}>
                  <Text style={styles.statLabel}>Bundles</Text>
                  <Text style={styles.statVal}>{item.bundles}</Text>
                </View>

                <View style={styles.statCol}>
                  <Text style={styles.statLabel}>Sheets/Bundle</Text>
                  <Text style={styles.statVal}>{item.sheets_per_bundle}</Text>
                </View>

                <View style={styles.statCol}>
                  <Text style={styles.statLabel}>Reorder Level</Text>
                  <Text style={styles.statVal}>{item.reorder_level}</Text>
                </View>
              </View>
            </View>
          )}
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
  headerBox: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0f172a',
  },
  headerSub: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 2,
  },
  alertBadge: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  alertText: {
    fontSize: 11,
    fontWeight: '800',
    color: '#dc2626',
  },
  stockCard: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  stockCardWarning: {
    borderColor: '#fca5a5',
    backgroundColor: '#fffdfd',
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 10,
  },
  itemName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0f172a',
  },
  itemCategory: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 2,
  },
  lowStockTag: {
    backgroundColor: '#fee2e2',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  lowStockTagText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#b91c1c',
  },
  inStockTag: {
    backgroundColor: '#ecfdf5',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  inStockTagText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#047857',
  },
  cardStatsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  statCol: {
    alignItems: 'center',
  },
  statLabel: {
    fontSize: 10,
    color: '#64748b',
    marginBottom: 2,
  },
  statVal: {
    fontSize: 14,
    fontWeight: '800',
    color: '#1e293b',
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
