import React, { useState } from 'react';
import {
  SafeAreaView,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  StatusBar,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { AuthProvider, useAuth } from './src/context/AuthContext';
import { LoginScreen } from './src/screens/LoginScreen';
import { BillingScreen } from './src/screens/BillingScreen';
import { SalesScreen } from './src/screens/SalesScreen';
import { StockScreen } from './src/screens/StockScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';

type TabType = 'billing' | 'sales' | 'stock' | 'settings';

const MainNavigator: React.FC = () => {
  const { user, isLoading } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>('billing');

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#6d28d9" />
        <Text style={styles.loadingText}>Starting Iread Billing...</Text>
      </View>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }

  return (
    <SafeAreaView style={styles.appContainer}>
      <StatusBar barStyle="dark-content" backgroundColor="#ffffff" />

      {/* Top Header */}
      <View style={styles.topHeader}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>IREAD BILLING</Text>
          <Text style={styles.headerStaffTag}>Staff: {user.name}</Text>
        </View>
        <View style={styles.headerRight}>
          <View style={styles.statusOnlinePill}>
            <View style={styles.onlineDot} />
            <Text style={styles.onlineText}>COUNTER POS</Text>
          </View>
        </View>
      </View>

      {/* Main Screen Content */}
      <View style={styles.screenContent}>
        {activeTab === 'billing' && <BillingScreen />}
        {activeTab === 'sales' && <SalesScreen />}
        {activeTab === 'stock' && <StockScreen />}
        {activeTab === 'settings' && <SettingsScreen />}
      </View>

      {/* Bottom Navigation Bar */}
      <View style={styles.bottomNav}>
        <TouchableOpacity
          style={[styles.navTab, activeTab === 'billing' && styles.navTabActive]}
          onPress={() => setActiveTab('billing')}
        >
          <Text style={styles.navIcon}>🧾</Text>
          <Text
            style={[
              styles.navLabel,
              activeTab === 'billing' && styles.navLabelActive,
            ]}
          >
            Billing
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.navTab, activeTab === 'sales' && styles.navTabActive]}
          onPress={() => setActiveTab('sales')}
        >
          <Text style={styles.navIcon}>📊</Text>
          <Text
            style={[
              styles.navLabel,
              activeTab === 'sales' && styles.navLabelActive,
            ]}
          >
            Sales
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.navTab, activeTab === 'stock' && styles.navTabActive]}
          onPress={() => setActiveTab('stock')}
        >
          <Text style={styles.navIcon}>📦</Text>
          <Text
            style={[
              styles.navLabel,
              activeTab === 'stock' && styles.navLabelActive,
            ]}
          >
            Stock
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.navTab, activeTab === 'settings' && styles.navTabActive]}
          onPress={() => setActiveTab('settings')}
        >
          <Text style={styles.navIcon}>⚙️</Text>
          <Text
            style={[
              styles.navLabel,
              activeTab === 'settings' && styles.navLabelActive,
            ]}
          >
            Settings
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <MainNavigator />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  appContainer: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#64748b',
    fontWeight: '600',
  },
  topHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  headerLeft: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: '900',
    color: '#1e1b4b',
    letterSpacing: 0.5,
  },
  headerStaffTag: {
    fontSize: 11,
    color: '#6b7280',
    marginTop: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusOnlinePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ecfdf5',
    borderWidth: 1,
    borderColor: '#a7f3d0',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 3,
    gap: 5,
  },
  onlineDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#10b981',
  },
  onlineText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#065f46',
  },
  screenContent: {
    flex: 1,
  },
  bottomNav: {
    flexDirection: 'row',
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    paddingVertical: 6,
    elevation: 8,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: -2 },
  },
  navTab: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 4,
  },
  navTabActive: {
    borderTopWidth: 2,
    borderTopColor: '#6d28d9',
    marginTop: -2,
  },
  navIcon: {
    fontSize: 18,
    marginBottom: 2,
  },
  navLabel: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '600',
  },
  navLabelActive: {
    color: '#6d28d9',
    fontWeight: '800',
  },
});
