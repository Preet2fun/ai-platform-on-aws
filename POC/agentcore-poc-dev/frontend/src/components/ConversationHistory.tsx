// frontend/src/components/ConversationHistory.tsx
/**
 * Displays a list of past conversations in the sidebar.
 * Clicking a conversation loads its history into the chat.
 */
import React, { useState, useEffect } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import { apiClient } from '../services/api/apiClient';
import { useChatStore } from '../store/chatStore';

interface Conversation {
  conversation_id: string;
  title: string;
  updated_at: string;
}

export function ConversationHistory() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { conversationId, loadConversation, clearMessages } = useChatStore();

  const fetchConversations = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getConversations();
      // Sort by updated_at: most recent first
      const sorted = [...data].sort((a: Conversation, b: Conversation) => {
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
      setConversations(sorted);
    } catch (e) {
      console.warn('Failed to load conversations:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  const handleSelect = (conv: Conversation) => {
    if (conv.conversation_id === conversationId) return;
    loadConversation(conv.conversation_id);
  };

  const handleNewChat = () => {
    clearMessages();
    fetchConversations();
  };

  const handleDelete = async (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiClient.deleteConversation(conv.conversation_id);
      setConversations(prev => prev.filter(c => c.conversation_id !== conv.conversation_id));
    } catch (err) {
      console.warn('Failed to delete conversation:', err);
    }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <Container header={
      <Header
        variant="h3"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button iconName="refresh" variant="icon" onClick={fetchConversations} loading={isLoading} />
            <Button iconName="add-plus" variant="icon" onClick={handleNewChat} />
          </SpaceBetween>
        }
      >
        Conversations
      </Header>
    }>
      <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
      <SpaceBetween size="xs">
        {conversations.length === 0 && !isLoading && (
          <Box variant="p" color="text-body-secondary" textAlign="center">
            No conversations yet
          </Box>
        )}
        {conversations.map(conv => (
          <div
            key={conv.conversation_id}
            onClick={() => handleSelect(conv)}
            style={{
              padding: '8px 10px',
              borderRadius: '6px',
              cursor: 'pointer',
              backgroundColor: conv.conversation_id === conversationId ? '#e8f4fd' : 'transparent',
              border: conv.conversation_id === conversationId ? '1px solid #0073bb' : '1px solid transparent',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div style={{ overflow: 'hidden', flex: 1 }}>
              <div style={{
                fontSize: '13px',
                fontWeight: conv.conversation_id === conversationId ? 600 : 400,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {conv.title || 'Untitled'}
              </div>
              <div style={{ fontSize: '11px', color: '#687078' }}>
                {formatTime(conv.updated_at)}
              </div>
            </div>
            <Button
              iconName="close"
              variant="icon"
              onClick={(e: any) => handleDelete(conv, e)}
            />
          </div>
        ))}
      </SpaceBetween>
      </div>
    </Container>
  );
}
