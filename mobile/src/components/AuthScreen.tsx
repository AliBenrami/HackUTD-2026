import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { supabase } from '../lib/supabase';
import { colors, fonts } from '../theme/colors';
import { AppText, Button } from './ui';

export function AuthScreen() {
  const [mode, setMode] = useState<'sign-in' | 'create'>('sign-in');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setMessage(null);
    try {
      if (mode === 'create') {
        const { data, error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { data: { display_name: name.trim() || 'You' } },
        });
        if (error) throw error;
        if (!data.session) {
          setMessage('Check your email to confirm the account, then sign in.');
          setMode('sign-in');
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error) throw error;
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View className="flex-1 justify-center bg-ink px-6">
      <AppText weight="semibold" className="text-3xl">
        Golf
        <AppText weight="semibold" className="text-3xl text-cyan">
          AR
        </AppText>
      </AppText>
      <AppText className="mt-2 text-base text-slate">
        {mode === 'create' ? 'Create an account for your rounds and swings.' : 'Sign in to your rounds and swings.'}
      </AppText>
      <View className="mt-8 gap-3">
        {mode === 'create' ? (
          <Field value={name} onChangeText={setName} placeholder="Name" autoCapitalize="words" />
        ) : null}
        <Field value={email} onChangeText={setEmail} placeholder="Email" keyboardType="email-address" autoCapitalize="none" />
        <Field value={password} onChangeText={setPassword} placeholder="Password" secureTextEntry />
        {message ? <AppText className="text-sm text-slate">{message}</AppText> : null}
        <Button
          label={busy ? 'Working…' : mode === 'create' ? 'Create account' : 'Sign in'}
          onPress={() => void submit()}
          disabled={busy || !email.trim() || password.length < 6}
        />
        <Button
          label={mode === 'create' ? 'I already have an account' : 'Create an account'}
          variant="secondary"
          onPress={() => {
            setMode(mode === 'create' ? 'sign-in' : 'create');
            setMessage(null);
          }}
        />
      </View>
    </View>
  );
}

function Field({
  value,
  onChangeText,
  placeholder,
  secureTextEntry = false,
  autoCapitalize = 'none',
  keyboardType = 'default',
}: {
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  secureTextEntry?: boolean;
  autoCapitalize?: 'none' | 'words';
  keyboardType?: 'default' | 'email-address';
}) {
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={colors.slate}
      secureTextEntry={secureTextEntry}
      autoCapitalize={autoCapitalize}
      keyboardType={keyboardType}
      autoCorrect={false}
      className="min-h-12 rounded-2xl border border-white/10 bg-panel px-4 text-base"
      style={{ fontFamily: fonts.regular, color: colors.mist }}
    />
  );
}
