import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { Platform } from 'react-native';

const preview = process.env.EXPO_PUBLIC_PREVIEW === '1';
const url = process.env.EXPO_PUBLIC_SUPABASE_URL || (preview ? 'https://preview.local' : '');
const key = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY || (preview ? 'preview-public-key' : '');

if (!url || !key) {
  throw new Error('Supabase URL and publishable key are missing.');
}

export const supabase = createClient(url, key, {
  auth: {
    storage: Platform.OS === 'web' ? undefined : AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
