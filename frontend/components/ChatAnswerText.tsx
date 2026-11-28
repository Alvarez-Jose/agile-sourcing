import React from 'react';
import type {FormLink} from '../services/agent';

function officialUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    if (!['ucsc.edu', 'ucop.edu'].some(host => url.hostname === host || url.hostname.endsWith('.' + host))) return null;
    return url.toString();
  } catch {return null;}
}

// Render plain text and verified form names only. Model-generated Markdown/HTML
// never supplies an executable link or markup.
export function ChatAnswerText({text, links = []}: {text: string; links?: FormLink[]}) {
  const plain = text.replace(/\[([^\]\n]+)\]\([^\s)]+\)/g, '$1');
  const choices = links.flatMap(link => {
    const url = officialUrl(link.url);
    return url && Array.isArray(link.aliases) ? link.aliases.filter(alias => typeof alias === 'string' && alias.length > 1)
      .map(alias => ({alias, url, title: link.title})) : [];
  }).sort((a, b) => b.alias.length - a.alias.length);
  if (!choices.length) return <span className="whitespace-pre-wrap">{plain}</span>;
  const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`(?<!\\w)(${choices.map(choice => escape(choice.alias)).join('|')})(?!\\w)`, 'gi');
  const parts: React.ReactNode[] = [];
  let end = 0;
  for (const match of plain.matchAll(pattern)) {
    const position = match.index!;
    if (position > end) parts.push(plain.slice(end, position));
    const choice = choices.find(candidate => candidate.alias.toLowerCase() === match[0].toLowerCase())!;
    if (match[0].toLowerCase() === 'sspr' && /^\s+(?:FAQ|frequently asked)/i.test(plain.slice(position + match[0].length))) {
      parts.push(match[0]);
    } else {
      parts.push(<a key={position} href={choice.url} title={`Open ${choice.title}`} target="_blank" rel="noopener noreferrer" className="text-[#00539b] underline underline-offset-2">{match[0]}</a>);
    }
    end = position + match[0].length;
  }
  parts.push(plain.slice(end));
  return <span className="whitespace-pre-wrap">{parts}</span>;
}
