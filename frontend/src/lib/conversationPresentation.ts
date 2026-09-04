type Message = { role: string; content: string; partial?: boolean; status?: string };
type ScrollPosition = { scrollHeight: number; scrollTop: number; clientHeight: number };

export function shouldFollowOutput(position: ScrollPosition): boolean {
  return position.scrollHeight - position.scrollTop - position.clientHeight <= 64;
}

export function canSaveAnswer(message: Message): boolean {
  return message.role === 'assistant' && Boolean(message.content) && !message.partial
    && (!message.status || message.status === 'complete');
}
