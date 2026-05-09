import type { Locale } from '../api/types';
import { en } from './en';
import { zh } from './zh';

export type Messages = typeof zh;

export function getMessages(locale: Locale): Messages {
  return locale === 'English' ? en : zh;
}
