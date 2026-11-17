import React, { useState, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  TextInput,
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
} from 'react-native';
import { ServiceItem, CartItem, PrintJob } from '../types';
import { api } from '../services/api';
import { PrintStatusModal } from '../components/PrintStatusModal';

export const BillingScreen: React.FC = () => {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  // Customer & Bill Details
  const [customer, setCustomer] = useState('');
  const [discount, setDiscount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<'Cash' | 'UPI' | 'Card'>('Cash');
  const [isPaid, setIsPaid] = useState<boolean>(true); // Petpooja-style toggle
  const [submitting, setSubmitting] = useState(false);

  // Print Modal
  const [modalVisible, setModalVisible] = useState(false);
  const [activePrintJob, setActivePrintJob] = useState<PrintJob | null>(null);
  const [lastBillNo, setLastBillNo] = useState('');

  // Load active services
  useEffect(() => {
    loadServices();
  }, []);

  const loadServices = async () => {
    setLoading(true);
    try {
      const data = await api.getServices();
      setServices(data);
    } catch (err: any) {
      Alert.alert('Catalog Error', err.message);
    } finally {
      setLoading(false);
    }
  };

  // Categories
  const categories = useMemo(() => {
    const cats = new Set<string>(['ALL']);
    services.forEach((s) => {
      const t = s.print_type.toUpperCase();
      cats.add(t);
    });
    return Array.from(cats);
  }, [services]);

  const filteredServices = useMemo(() => {
    if (selectedCategory === 'ALL') return services;
    return services.filter((s) => s.print_type.toUpperCase() === selectedCategory);
  }, [services, selectedCategory]);

  // Pricing calculation helper
  const calculateItemPrice = (
    service: ServiceItem,
    copies: number,
    sides: 'Single' | 'Double'
  ): { lineTotal: number; unitRate: number } => {
    const isDouble = sides === 'Double';
    const firstCopy = isDouble && service.double_rate != null ? service.double_rate : service.rate;

    if (service.extra_copy_rate != null && service.extra_copy_rate > 0) {
      // Tiered pricing (e.g. Print B&W A4)
      const extraRate = service.extra_copy_rate;
      const total = firstCopy + Math.max(0, copies - 1) * extraRate;
      const rate = total / copies;
      return { lineTotal: Math.round(total * 100) / 100, unitRate: Math.round(rate * 100) / 100 };
    } else {
      const rate = firstCopy;
      const total = copies * rate;
      return { lineTotal: Math.round(total * 100) / 100, unitRate: rate };
    }
  };

  // Add item to cart
  const addToCart = (service: ServiceItem, sides: 'Single' | 'Double' = 'Single') => {
    setCart((prev) => {
      const existingIdx = prev.findIndex(
        (item) => item.service_id === service.id && item.sides === sides
      );

      if (existingIdx >= 0) {
        // Increase copies
        const updated = [...prev];
        const currentCopies = updated[existingIdx].quantity + 1;
        const calc = calculateItemPrice(service, currentCopies, sides);
        updated[existingIdx] = {
          ...updated[existingIdx],
          quantity: currentCopies,
          line_total: calc.lineTotal,
          rate: calc.unitRate,
        };
        return updated;
      } else {
        const calc = calculateItemPrice(service, 1, sides);
        const newItem: CartItem = {
          service_id: service.id,
          service_name: service.name,
          quantity: 1,
          pages_per_copy: 1,
          sides,
          rate: calc.unitRate,
          line_total: calc.lineTotal,
          paper_size: service.paper_size,
          print_type: service.print_type,
        };
        return [...prev, newItem];
      }
    });
  };

  // Update item copies
  const updateCopies = (index: number, delta: number) => {
    setCart((prev) => {
      const updated = [...prev];
      const it = updated[index];
      const newQty = it.quantity + delta;
      if (newQty <= 0) {
        updated.splice(index, 1);
        return updated;
      }

      const sObj = services.find((s) => s.id === it.service_id);
      if (sObj) {
        const calc = calculateItemPrice(sObj, newQty, it.sides);
        updated[index] = {
          ...it,
          quantity: newQty,
          line_total: calc.lineTotal,
          rate: calc.unitRate,
        };
      } else {
        updated[index] = {
          ...it,
          quantity: newQty,
          line_total: Math.round(newQty * it.rate * 100) / 100,
        };
      }
      return updated;
    });
  };

  // Toggle item side
  const toggleSide = (index: number) => {
    setCart((prev) => {
      const updated = [...prev];
      const it = updated[index];
      const newSide: 'Single' | 'Double' = it.sides === 'Single' ? 'Double' : 'Single';
      const sObj = services.find((s) => s.id === it.service_id);

      if (sObj && sObj.double_rate != null) {
        const calc = calculateItemPrice(sObj, it.quantity, newSide);
        updated[index] = {
          ...it,
          sides: newSide,
          line_total: calc.lineTotal,
          rate: calc.unitRate,
        };
      } else if (sObj) {
        Alert.alert('Notice', 'Double side option not configured for this service.');
      }
      return updated;
    });
  };

  const removeItem = (index: number) => {
    setCart((prev) => prev.filter((_, i) => i !== index));
  };

  // Cart Calculations
  const subtotal = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.line_total, 0);
  }, [cart]);

  const numDiscount = useMemo(() => {
    const val = parseFloat(discount);
    return isNaN(val) || val < 0 ? 0 : Math.min(val, subtotal);
  }, [discount, subtotal]);

  const grandTotal = useMemo(() => {
    return Math.max(0, Math.round((subtotal - numDiscount) * 100) / 100);
  }, [subtotal, numDiscount]);

  // Submit Bill
  const handleSubmitBill = async (action: 'save_only' | 'save_and_print') => {
    if (cart.length === 0) {
      Alert.alert('Cart Empty', 'Please add at least one service item to the bill.');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        customer: customer.trim() || 'Walk-in Customer',
        payment_method: paymentMethod,
        payment_status: isPaid ? ('Paid' as const) : ('Unpaid' as const),
        discount: numDiscount,
        paid: isPaid ? grandTotal : 0,
        action,
        items: cart.map((item) => ({
          service_id: item.service_id,
          service_name: item.service_name,
          quantity: item.quantity,
          pages_per_copy: 1,
          sides: item.sides,
          rate: item.rate,
          line_total: item.line_total,
        })),
      };

      const res = await api.createBill(payload);

      if (res.success) {
        setLastBillNo(res.bill_no);
        if (action === 'save_and_print' && res.print_job) {
          setActivePrintJob(res.print_job);
          setModalVisible(true);
        } else {
          Alert.alert(
            '✓ Bill Saved',
            `Bill ${res.bill_no} saved successfully (Status: ${isPaid ? 'Paid' : 'Unpaid'}, Total: ₹${grandTotal}).`
          );
        }
        // Reset Cart
        setCart([]);
        setCustomer('');
        setDiscount('');
        setIsPaid(true);
      }
    } catch (err: any) {
      Alert.alert('Billing Error', err.message || 'Failed to save bill.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Category Filter Pills */}
      <View style={styles.categoryBar}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat}
              style={[
                styles.categoryPill,
                selectedCategory === cat && styles.categoryPillActive,
              ]}
              onPress={() => setSelectedCategory(cat)}
            >
              <Text
                style={[
                  styles.categoryPillText,
                  selectedCategory === cat && styles.categoryPillTextActive,
                ]}
              >
                {cat}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Main Layout: Service Grid & Cart */}
      <View style={styles.mainLayout}>
        {/* Left: Quick Item Catalog Grid */}
        <View style={styles.catalogContainer}>
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color="#6d28d9" size="large" />
          ) : (
            <FlatList
              data={filteredServices}
              keyExtractor={(item) => item.id.toString()}
              numColumns={2}
              columnWrapperStyle={{ gap: 8 }}
              contentContainerStyle={{ paddingBottom: 16, gap: 8 }}
              renderItem={({ item }) => (
                <View style={styles.itemCard}>
                  <Text style={styles.itemTitle} numberOfLines={2}>
                    {item.name}
                  </Text>
                  <Text style={styles.itemSizeBadge}>{item.paper_size || 'Std'}</Text>
                  <Text style={styles.itemPrice}>
                    ₹{item.rate.toFixed(2)}
                    {item.double_rate != null ? ` / ₹${item.double_rate.toFixed(2)}` : ''}
                  </Text>

                  {/* Add Buttons */}
                  <View style={styles.itemBtnRow}>
                    <TouchableOpacity
                      style={styles.addBtnSingle}
                      onPress={() => addToCart(item, 'Single')}
                    >
                      <Text style={styles.addBtnText}>+ Single</Text>
                    </TouchableOpacity>
                    {item.double_rate != null && (
                      <TouchableOpacity
                        style={styles.addBtnDouble}
                        onPress={() => addToCart(item, 'Double')}
                      >
                        <Text style={styles.addBtnText}>+ Double</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              )}
            />
          )}
        </View>

        {/* Right / Bottom: Bill Cart & Checkout */}
        <View style={styles.cartContainer}>
          <Text style={styles.cartHeader}>Bill Cart ({cart.length})</Text>

          {cart.length === 0 ? (
            <View style={styles.emptyCartBox}>
              <Text style={{ fontSize: 24, marginBottom: 6 }}>🛒</Text>
              <Text style={styles.emptyCartText}>No items added to bill yet.</Text>
              <Text style={{ fontSize: 11, color: '#9ca3af', textAlign: 'center' }}>
                Tap items on the left to add them to the bill.
              </Text>
            </View>
          ) : (
            <ScrollView style={styles.cartList} showsVerticalScrollIndicator={false}>
              {cart.map((item, idx) => (
                <View key={`${item.service_id}-${item.sides}-${idx}`} style={styles.cartRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.cartItemName} numberOfLines={1}>
                      {item.service_name}
                    </Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 }}>
                      <TouchableOpacity onPress={() => toggleSide(idx)}>
                        <Text style={styles.cartSideBadge}>
                          {item.sides === 'Double' ? 'Double Side (D)' : 'Single Side (S)'} ↻
                        </Text>
                      </TouchableOpacity>
                      <Text style={styles.cartUnitRate}>@ ₹{item.rate.toFixed(2)}</Text>
                    </View>
                  </View>

                  {/* Quantity Stepper */}
                  <View style={styles.stepper}>
                    <TouchableOpacity style={styles.stepBtn} onPress={() => updateCopies(idx, -1)}>
                      <Text style={styles.stepBtnText}>−</Text>
                    </TouchableOpacity>
                    <Text style={styles.qtyText}>{item.quantity}</Text>
                    <TouchableOpacity style={styles.stepBtn} onPress={() => updateCopies(idx, 1)}>
                      <Text style={styles.stepBtnText}>+</Text>
                    </TouchableOpacity>
                  </View>

                  {/* Line Total */}
                  <Text style={styles.cartLineTotal}>₹{item.line_total.toFixed(2)}</Text>

                  {/* Remove */}
                  <TouchableOpacity onPress={() => removeItem(idx)} style={styles.removeBtn}>
                    <Text style={styles.removeBtnText}>✕</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </ScrollView>
          )}

          {/* Customer & Discount Controls */}
          <View style={styles.checkoutMeta}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TextInput
                style={[styles.inputField, { flex: 2 }]}
                placeholder="Customer Name (Optional)"
                placeholderTextColor="#9ca3af"
                value={customer}
                onChangeText={setCustomer}
              />
              <TextInput
                style={[styles.inputField, { flex: 1 }]}
                placeholder="Discount ₹"
                placeholderTextColor="#9ca3af"
                keyboardType="numeric"
                value={discount}
                onChangeText={setDiscount}
              />
            </View>

            {/* Payment Method & Petpooja-style Paid / Unpaid Option */}
            <View style={styles.paymentControlsRow}>
              {/* Payment Status: Petpooja Checkbox Toggle */}
              <TouchableOpacity
                style={[styles.statusToggle, isPaid ? styles.statusPaid : styles.statusUnpaid]}
                onPress={() => setIsPaid(!isPaid)}
              >
                <Text style={styles.statusToggleIcon}>{isPaid ? '✓' : '○'}</Text>
                <Text style={[styles.statusToggleText, { color: isPaid ? '#065f46' : '#991b1b' }]}>
                  {isPaid ? 'PAID' : 'UNPAID'}
                </Text>
              </TouchableOpacity>

              {/* Payment Method selector */}
              <View style={styles.methodPillGroup}>
                {(['Cash', 'UPI', 'Card'] as const).map((m) => (
                  <TouchableOpacity
                    key={m}
                    style={[styles.methodPill, paymentMethod === m && styles.methodPillActive]}
                    onPress={() => setPaymentMethod(m)}
                  >
                    <Text
                      style={[
                        styles.methodPillText,
                        paymentMethod === m && styles.methodPillTextActive,
                      ]}
                    >
                      {m}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          </View>

          {/* Grand Total Bar */}
          <View style={styles.totalBar}>
            <View>
              <Text style={styles.totalLabel}>
                Subtotal: ₹{subtotal.toFixed(2)} {numDiscount > 0 ? `| -₹${numDiscount}` : ''}
              </Text>
              <Text style={styles.grandTotalText}>₹{grandTotal.toFixed(2)}</Text>
            </View>

            {/* Action Buttons: Save Only vs Save & Print */}
            <View style={styles.actionBtnRow}>
              <TouchableOpacity
                style={[styles.actionBtn, styles.saveOnlyBtn, submitting && styles.btnDisabled]}
                onPress={() => handleSubmitBill('save_only')}
                disabled={submitting}
              >
                <Text style={styles.saveOnlyText}>Save Only</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.actionBtn, styles.savePrintBtn, submitting && styles.btnDisabled]}
                onPress={() => handleSubmitBill('save_and_print')}
                disabled={submitting}
              >
                {submitting ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.savePrintText}>🖨️ Save &amp; Print</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </View>

      {/* Real-time Thermal Print Status Modal */}
      <PrintStatusModal
        visible={modalVisible}
        initialJob={activePrintJob}
        billNo={lastBillNo}
        onClose={() => {
          setModalVisible(false);
          setActivePrintJob(null);
        }}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  categoryBar: {
    backgroundColor: '#ffffff',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  categoryPill: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    marginRight: 8,
  },
  categoryPillActive: {
    backgroundColor: '#6d28d9',
  },
  categoryPillText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#475569',
  },
  categoryPillTextActive: {
    color: '#ffffff',
  },
  mainLayout: {
    flex: 1,
    flexDirection: Platform.OS === 'web' ? 'row' : 'column',
  },
  catalogContainer: {
    flex: 1,
    padding: 10,
  },
  itemCard: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    elevation: 1,
    shadowColor: '#000',
    shadowOpacity: 0.04,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 1 },
  },
  itemTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1e293b',
    minHeight: 34,
  },
  itemSizeBadge: {
    fontSize: 10,
    color: '#64748b',
    marginTop: 2,
  },
  itemPrice: {
    fontSize: 14,
    fontWeight: '800',
    color: '#6d28d9',
    marginTop: 4,
    marginBottom: 6,
  },
  itemBtnRow: {
    flexDirection: 'row',
    gap: 4,
  },
  addBtnSingle: {
    flex: 1,
    backgroundColor: '#6d28d9',
    borderRadius: 6,
    paddingVertical: 6,
    alignItems: 'center',
  },
  addBtnDouble: {
    flex: 1,
    backgroundColor: '#0284c7',
    borderRadius: 6,
    paddingVertical: 6,
    alignItems: 'center',
  },
  addBtnText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '700',
  },
  cartContainer: {
    flex: 1.2,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    padding: 12,
  },
  cartHeader: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0f172a',
    marginBottom: 8,
  },
  emptyCartBox: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  emptyCartText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#64748b',
  },
  cartList: {
    flex: 1,
  },
  cartRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    gap: 8,
  },
  cartItemName: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1e293b',
  },
  cartSideBadge: {
    fontSize: 10,
    fontWeight: '700',
    color: '#0284c7',
    backgroundColor: '#e0f2fe',
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderRadius: 4,
  },
  cartUnitRate: {
    fontSize: 11,
    color: '#64748b',
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    borderRadius: 6,
  },
  stepBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  stepBtnText: {
    fontSize: 14,
    fontWeight: '800',
    color: '#334155',
  },
  qtyText: {
    fontSize: 13,
    fontWeight: '800',
    paddingHorizontal: 6,
    color: '#0f172a',
  },
  cartLineTotal: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0f172a',
    minWidth: 50,
    textAlign: 'right',
  },
  removeBtn: {
    padding: 4,
  },
  removeBtnText: {
    fontSize: 14,
    color: '#ef4444',
    fontWeight: '700',
  },
  checkoutMeta: {
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    gap: 8,
  },
  inputField: {
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 12,
    color: '#0f172a',
  },
  paymentControlsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  statusToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1.5,
    gap: 6,
  },
  statusPaid: {
    backgroundColor: '#ecfdf5',
    borderColor: '#10b981',
  },
  statusUnpaid: {
    backgroundColor: '#fef2f2',
    borderColor: '#ef4444',
  },
  statusToggleIcon: {
    fontSize: 14,
    fontWeight: '900',
  },
  statusToggleText: {
    fontSize: 12,
    fontWeight: '800',
  },
  methodPillGroup: {
    flexDirection: 'row',
    gap: 4,
  },
  methodPill: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 6,
    backgroundColor: '#f1f5f9',
  },
  methodPillActive: {
    backgroundColor: '#1e293b',
  },
  methodPillText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#475569',
  },
  methodPillTextActive: {
    color: '#ffffff',
  },
  totalBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    marginTop: 6,
  },
  totalLabel: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '600',
  },
  grandTotalText: {
    fontSize: 20,
    fontWeight: '900',
    color: '#0f172a',
  },
  actionBtnRow: {
    flexDirection: 'row',
    gap: 8,
  },
  actionBtn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveOnlyBtn: {
    backgroundColor: '#f1f5f9',
    borderWidth: 1,
    borderColor: '#cbd5e1',
  },
  saveOnlyText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '800',
  },
  savePrintBtn: {
    backgroundColor: '#10b981',
  },
  savePrintText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  btnDisabled: {
    opacity: 0.5,
  },
});
