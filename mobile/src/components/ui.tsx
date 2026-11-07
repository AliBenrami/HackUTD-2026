import { ChevronLeft } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, Text, View, type PressableProps, type TextProps } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, fonts, type FontWeight } from '../theme/colors';

const textColors: Record<string, string> = {
  'text-mist': colors.mist,
  'text-slate': colors.slate,
  'text-cyan': colors.cyan,
  'text-ink': colors.ink,
  'text-magenta': colors.magenta,
  'text-violet': colors.violet,
};

function textColor(className?: string): string {
  const tokens = className?.split(/\s+/) ?? [];
  for (const token of tokens) {
    const match = textColors[token];
    if (match) return match;
  }
  return colors.mist;
}

export function AppText({
  weight = 'regular',
  className,
  style,
  ...props
}: TextProps & { weight?: FontWeight; className?: string }) {
  return (
    <Text
      className={className}
      style={[{ fontFamily: fonts[weight], color: textColor(className) }, style]}
      {...props}
    />
  );
}

export function Screen({
  children,
  header,
  padded = true,
}: {
  children: ReactNode;
  header?: ReactNode;
  padded?: boolean;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View className="flex-1 bg-ink">
      {header ? (
        <View style={{ paddingTop: insets.top + 8, paddingHorizontal: 20 }}>{header}</View>
      ) : null}
      <ScrollView
        className="flex-1"
        contentContainerStyle={{
          paddingTop: header ? 8 : insets.top + 16,
          paddingBottom: 112,
          paddingHorizontal: padded ? 20 : 0,
        }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {children}
      </ScrollView>
    </View>
  );
}

export function BackHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <View className="mb-2 flex-row items-center">
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Go back"
        onPress={onBack}
        className="h-11 w-11 items-center justify-center rounded-full bg-panel"
      >
        <ChevronLeft color={colors.mist} size={22} />
      </Pressable>
      <AppText weight="semibold" className="ml-3 text-xl">
        {title}
      </AppText>
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  icon,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  icon?: ReactNode;
}) {
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      className={`min-h-14 flex-row items-center justify-center gap-2 rounded-2xl px-5 ${
        primary ? 'bg-cyan' : 'border border-white/10 bg-panel'
      }`}
      style={({ pressed }) => ({ opacity: disabled ? 0.4 : pressed ? 0.84 : 1 })}
    >
      {icon}
      <AppText weight="semibold" className={`text-base ${primary ? 'text-ink' : 'text-mist'}`}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function IconButton({
  label,
  onPress,
  disabled,
  children,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      className="h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-panel"
      style={({ pressed }) => ({ opacity: disabled ? 0.35 : pressed ? 0.8 : 1 })}
    >
      {children}
    </Pressable>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <View className={`rounded-3xl border border-white/10 bg-panel ${className}`}>{children}</View>;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View className="flex-row rounded-full bg-panel p-1">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            onPress={() => onChange(option.value)}
            className={`min-h-11 flex-1 items-center justify-center rounded-full px-3 ${
              selected ? 'bg-cyan' : ''
            }`}
          >
            <AppText weight="medium" className={`text-sm ${selected ? 'text-ink' : 'text-slate'}`}>
              {option.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Wordmark() {
  return (
    <Text accessibilityRole="header">
      <AppText weight="semibold" className="text-[28px]">
        Golf
      </AppText>
      <AppText weight="semibold" className="text-[28px] text-cyan">
        AR
      </AppText>
    </Text>
  );
}

export function PressableCard({
  onPress,
  children,
  className = '',
  ...props
}: PressableProps & { className?: string; children: ReactNode }) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      className={`rounded-3xl border border-white/10 bg-panel ${className}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.86 : 1 })}
      {...props}
    >
      {children}
    </Pressable>
  );
}
