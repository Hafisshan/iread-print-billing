import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';

export const LoginScreen: React.FC = () => {
  const { login, serverUrl, updateServerUrl } = useAuth();
  const [username, setUsername] = useState('staff');
  const [password, setPassword] = useState('iread@staff123');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [editingUrl, setEditingUrl] = useState(serverUrl);

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setErrorMsg('Please enter both username and password.');
      return;
    }
    setLoading(true);
    setErrorMsg('');
    try {
      await login(username.trim(), password);
    } catch (err: any) {
      setErrorMsg(err.message || 'Login failed. Please check credentials and server connection.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveUrl = async () => {
    if (!editingUrl.trim()) return;
    try {
      await updateServerUrl(editingUrl.trim());
      setShowServerConfig(false);
      Alert.alert('Server Configured', `Connected to ${editingUrl.trim()}`);
    } catch (err: any) {
      Alert.alert('Error', err.message);
    }
  };

  const handleTestConnection = async () => {
    setLoading(true);
    try {
      const res = await api.testConnection();
      if (res.ok) {
        Alert.alert('Connection Successful', `Server is reachable! Printer Service is: ${res.status?.toUpperCase()}`);
      } else {
        Alert.alert('Connection Failed', res.error || 'Server unreachable.');
      }
    } catch (e: any) {
      Alert.alert('Connection Error', e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}
    >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        {/* Brand Header */}
        <View style={styles.brandHeader}>
          <View style={styles.logoBadge}>
            <Text style={styles.logoIcon}>🖨️</Text>
          </View>
          <Text style={styles.brandTitle}>IREAD STATIONS</Text>
          <Text style={styles.brandSubtitle}>Staff Mobile Billing &amp; Thermal Print</Text>
        </View>

        {/* Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Staff Counter Login</Text>

          {errorMsg ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>⚠️ {errorMsg}</Text>
            </View>
          ) : null}

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Username</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. staff"
              placeholderTextColor="#9ca3af"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              placeholderTextColor="#9ca3af"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
            />
          </View>

          <TouchableOpacity
            style={[styles.loginBtn, loading && styles.btnDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <Text style={styles.loginBtnText}>Sign In to Counter</Text>
            )}
          </TouchableOpacity>

          {/* Quick Staff Credentials Hint */}
          <View style={styles.hintBox}>
            <Text style={styles.hintText}>Staff: staff / iread@staff123</Text>
            <Text style={styles.hintText}>Admin: admin / iread@123</Text>
          </View>
        </View>

        {/* Server Host / Wi-Fi Config Section */}
        <View style={styles.serverSection}>
          <TouchableOpacity
            style={styles.serverToggle}
            onPress={() => {
              setEditingUrl(serverUrl);
              setShowServerConfig(!showServerConfig);
            }}
          >
            <Text style={styles.serverToggleText}>
              🌐 Server Host: <Text style={{ fontWeight: '700' }}>{serverUrl || 'Default'}</Text> {showServerConfig ? '▲' : '▼'}
            </Text>
          </TouchableOpacity>

          {showServerConfig && (
            <View style={styles.serverConfigBox}>
              <Text style={styles.serverHelpText}>
                Enter the PC or Server IP running on the shop Wi-Fi network:
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
              <View style={styles.serverBtnRow}>
                <TouchableOpacity style={styles.serverSaveBtn} onPress={handleSaveUrl}>
                  <Text style={styles.serverSaveBtnText}>Save Server URL</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.serverTestBtn} onPress={handleTestConnection}>
                  <Text style={styles.serverTestBtnText}>Test Link</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
  },
  brandHeader: {
    alignItems: 'center',
    marginBottom: 28,
  },
  logoBadge: {
    width: 68,
    height: 68,
    borderRadius: 20,
    backgroundColor: '#6d28d9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
    elevation: 4,
    shadowColor: '#6d28d9',
    shadowOpacity: 0.3,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
  },
  logoIcon: {
    fontSize: 32,
  },
  brandTitle: {
    fontSize: 24,
    fontWeight: '900',
    color: '#1f2937',
    letterSpacing: 1,
  },
  brandSubtitle: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 4,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 22,
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 2 },
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 16,
  },
  errorBox: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: 8,
    padding: 10,
    marginBottom: 14,
  },
  errorText: {
    color: '#b91c1c',
    fontSize: 12,
    fontWeight: '600',
  },
  inputGroup: {
    marginBottom: 14,
  },
  label: {
    fontSize: 12,
    fontWeight: '700',
    color: '#374151',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  input: {
    backgroundColor: '#f9fafb',
    borderWidth: 1.5,
    borderColor: '#e5e7eb',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#111827',
  },
  loginBtn: {
    backgroundColor: '#6d28d9',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  btnDisabled: {
    opacity: 0.6,
  },
  loginBtnText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  hintBox: {
    marginTop: 16,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#f3f4f6',
    alignItems: 'center',
  },
  hintText: {
    fontSize: 11,
    color: '#9ca3af',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginTop: 2,
  },
  serverSection: {
    marginTop: 24,
    alignItems: 'center',
  },
  serverToggle: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: '#e5e7eb',
    borderRadius: 20,
  },
  serverToggleText: {
    fontSize: 12,
    color: '#4b5563',
  },
  serverConfigBox: {
    width: '100%',
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 14,
    marginTop: 10,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  serverHelpText: {
    fontSize: 11,
    color: '#6b7280',
    marginBottom: 8,
  },
  serverInput: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  serverBtnRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  serverSaveBtn: {
    flex: 1,
    backgroundColor: '#6d28d9',
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
  },
  serverSaveBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  serverTestBtn: {
    backgroundColor: '#e5e7eb',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  serverTestBtnText: {
    color: '#374151',
    fontSize: 12,
    fontWeight: '700',
  },
});
