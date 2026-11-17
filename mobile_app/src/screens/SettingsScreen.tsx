import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { PrinterStatusInfo } from '../types';

export const SettingsScreen: React.FC = () => {
  const { user, logout, serverUrl, updateServerUrl } = useAuth();
  const [editingUrl, setEditingUrl] = useState(serverUrl);
  const [savingUrl, setSavingUrl] = useState(false);
  const [testing, setTesting] = useState(false);
  const [printerInfo, setPrinterInfo] = useState<PrinterStatusInfo | null>(null);
  const [loadingPrinter, setLoadingPrinter] = useState(false);

  useEffect(() => {
    setEditingUrl(serverUrl);
    fetchPrinterStatus();
  }, [serverUrl]);

  const fetchPrinterStatus = async () => {
    setLoadingPrinter(true);
    try {
      const info = await api.getPrinterStatus();
      setPrinterInfo(info);
    } catch {
      // offline or unreachable
    } finally {
      setLoadingPrinter(false);
    }
  };

  const handleSaveUrl = async () => {
    if (!editingUrl.trim()) return;
    setSavingUrl(true);
    try {
      await updateServerUrl(editingUrl.trim());
      Alert.alert('Success', 'Server URL updated successfully.');
      fetchPrinterStatus();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setSavingUrl(false);
    }
  };

  const handleTestLink = async () => {
    setTesting(true);
    try {
      const res = await api.testConnection();
      if (res.ok) {
        Alert.alert(
          'Connection OK',
          `Server reached successfully!\nPC Thermal Print Service: ${res.status?.toUpperCase()}`
        );
        fetchPrinterStatus();
      } else {
        Alert.alert('Connection Failed', res.error || 'Server unreachable.');
      }
    } catch (e: any) {
      Alert.alert('Error', e.message);
    } finally {
      setTesting(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Sign Out', 'Are you sure you want to log out of the counter app?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Log Out', style: 'destructive', onPress: () => logout() },
    ]);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 16, gap: 16 }}>
      {/* User Profile Card */}
      <View style={styles.card}>
        <View style={styles.userRow}>
          <View style={styles.userAvatar}>
            <Text style={styles.userAvatarText}>
              {(user?.name || 'S').charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.userName}>{user?.name || 'Staff User'}</Text>
            <Text style={styles.userRole}>
              Logged in as: <Text style={{ fontWeight: '700' }}>{user?.username}</Text> (Role: {user?.role})
            </Text>
          </View>
        </View>
      </View>

      {/* PC Thermal Printer Link Status */}
      <View style={styles.card}>
        <View style={styles.cardHeaderRow}>
          <Text style={styles.cardTitle}>PC Wi-Fi Printer Host</Text>
          <TouchableOpacity onPress={fetchPrinterStatus} disabled={loadingPrinter}>
            <Text style={styles.refreshText}>{loadingPrinter ? '...' : '↻ Refresh'}</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.printerStatusBox}>
          <View style={styles.statusIndicatorRow}>
            <View
              style={[
                styles.statusDot,
                { backgroundColor: printerInfo?.is_online ? '#10b981' : '#ef4444' },
              ]}
            />
            <Text
              style={[
                styles.statusText,
                { color: printerInfo?.is_online ? '#065f46' : '#991b1b' },
              ]}
            >
              PC SERVICE: {printerInfo?.is_online ? 'ONLINE' : 'OFFLINE'}
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Thermal Width:</Text>
            <Text style={styles.infoVal}>{printerInfo?.thermal_width || '80mm'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Printer Target:</Text>
            <Text style={styles.infoVal}>{printerInfo?.default_printer || '__DEFAULT__'}</Text>
          </View>
          {printerInfo?.pc_info && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>PC Host:</Text>
              <Text style={styles.infoVal}>
                {printerInfo.pc_info.hostname} ({printerInfo.pc_info.os})
              </Text>
            </View>
          )}
        </View>

        <Text style={styles.printerHelp}>
          Staff phones send bills over Wi-Fi to the server. The Counter PC service automatically
          fetches and prints receipts without requiring USB cables on phones.
        </Text>
      </View>

      {/* Server Endpoint Configuration */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Backend Server Configuration</Text>
        <Text style={styles.cardSub}>
          Connects staff app to shop billing backend and printer spooler.
        </Text>

        <TextInput
          style={styles.serverInput}
          value={editingUrl}
          onChangeText={setEditingUrl}
          placeholder="http://192.168.1.100:5000"
          placeholderTextColor="#9ca3af"
          autoCapitalize="none"
          autoCorrect={false}
        />

        <View style={styles.btnRow}>
          <TouchableOpacity
            style={[styles.btn, styles.saveBtn]}
            onPress={handleSaveUrl}
            disabled={savingUrl}
          >
            {savingUrl ? (
              <ActivityIndicator color="#ffffff" size="small" />
            ) : (
              <Text style={styles.saveBtnText}>Save URL</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.testBtn]}
            onPress={handleTestLink}
            disabled={testing}
          >
            {testing ? (
              <ActivityIndicator color="#374151" size="small" />
            ) : (
              <Text style={styles.testBtnText}>Test Connection</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* Logout */}
      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Text style={styles.logoutBtnText}>Log Out from Counter</Text>
      </TouchableOpacity>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  userAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#6d28d9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  userAvatarText: {
    fontSize: 20,
    fontWeight: '900',
    color: '#ffffff',
  },
  userName: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0f172a',
  },
  userRole: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#0f172a',
  },
  cardSub: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 12,
  },
  refreshText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#6d28d9',
  },
  printerStatusBox: {
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    gap: 6,
  },
  statusIndicatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  infoLabel: {
    fontSize: 12,
    color: '#64748b',
  },
  infoVal: {
    fontSize: 12,
    fontWeight: '700',
    color: '#1e293b',
  },
  printerHelp: {
    fontSize: 11,
    color: '#94a3b8',
    marginTop: 10,
    lineHeight: 16,
  },
  serverInput: {
    backgroundColor: '#f8fafc',
    borderWidth: 1.5,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#0f172a',
    fontFamily: 'monospace',
    marginBottom: 12,
  },
  btnRow: {
    flexDirection: 'row',
    gap: 10,
  },
  btn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveBtn: {
    backgroundColor: '#6d28d9',
  },
  saveBtnText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '700',
  },
  testBtn: {
    backgroundColor: '#e2e8f0',
  },
  testBtnText: {
    color: '#334155',
    fontSize: 13,
    fontWeight: '700',
  },
  logoutBtn: {
    backgroundColor: '#fee2e2',
    borderWidth: 1,
    borderColor: '#fca5a5',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 30,
  },
  logoutBtnText: {
    color: '#b91c1c',
    fontSize: 14,
    fontWeight: '800',
  },
});
