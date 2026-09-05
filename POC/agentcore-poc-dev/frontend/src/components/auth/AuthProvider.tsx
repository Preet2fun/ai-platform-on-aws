// AuthProvider — Cognito authentication context with httpOnly cookie session management.
import React, { createContext, useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  RespondToAuthChallengeCommand,
  GlobalSignOutCommand,
} from '@aws-sdk/client-cognito-identity-provider';
import { apiClient, setAuthToken } from '../../services/api/apiClient';

interface AuthUser {
  user_id: string;
  email: string;
  username: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  completePasswordChange: (cognitoUser: any, newPassword: string, attributes: any) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

const getConfig = () => {
  const cfg = (window as any).__CONFIG__ || {};
  return {
    userPoolId: cfg.cognitoUserPoolId || '',
    clientId: cfg.cognitoClientId || '',
    region: cfg.region || '',
  };
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  const config = useMemo(() => getConfig(), []);
  const cognitoClient = useMemo(
    () => new CognitoIdentityProviderClient({ region: config.region }),
    [config.region]
  );

  // In-memory token (not persisted to localStorage)
  let _inMemoryIdToken: string | null = null;

  const storeTokens = useCallback((result: any) => {
    const auth = result.AuthenticationResult;
    if (auth) {
      // Tokens stored in httpOnly cookies by backend (/auth/set-refresh)
      // Keep id_token in memory only for parseIdToken (not persisted)
      _inMemoryIdToken = auth.IdToken;
      setAuthToken(auth.IdToken);
    }
  }, []);

  const parseIdToken = useCallback((token: string): AuthUser | null => {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return {
        user_id: payload.sub,
        email: payload.email || payload['cognito:username'],
        username: payload['cognito:username'] || payload.email,
      };
    } catch { return null; }
  }, []);

  // Restore session on mount via httpOnly cookie
  useEffect(() => {
    apiClient.restoreSession().then((data: any) => {
      if (data?.idToken || data?.id_token) {
        const token = data.idToken || data.id_token;
        _inMemoryIdToken = token;
        setAuthToken(token);
        setUser(parseIdToken(token));
      }
    }).catch(() => {}).finally(() => setIsLoading(false));
  }, [parseIdToken]);

  const signIn = useCallback(async (email: string, password: string) => {
    const cmd = new InitiateAuthCommand({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: config.clientId,
      AuthParameters: { USERNAME: email, PASSWORD: password },
    });
    const result = await cognitoClient.send(cmd);

    if (result.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
      const error: any = new Error('New password required');
      error.name = 'NewPasswordRequired';
      error.cognitoUser = { session: result.Session, username: email };
      error.userAttributes = JSON.parse(result.ChallengeParameters?.userAttributes || '{}');
      throw error;
    }

    storeTokens(result);
    const parsed = parseIdToken(result.AuthenticationResult!.IdToken!);
    setUser(parsed);

    // Persist refresh token and session token as httpOnly cookies
    try {
      await apiClient.setRefreshToken(
        result.AuthenticationResult!.RefreshToken!,
        result.AuthenticationResult!.IdToken!
      );
    } catch (e) { console.warn('Failed to persist refresh cookie:', e); }

    navigate('/app');
  }, [config.clientId, cognitoClient, storeTokens, parseIdToken, navigate]);

  const completePasswordChange = useCallback(async (cognitoUser: any, newPassword: string, attributes: any) => {
    const cmd = new RespondToAuthChallengeCommand({
      ChallengeName: 'NEW_PASSWORD_REQUIRED',
      ClientId: config.clientId,
      Session: cognitoUser.session,
      ChallengeResponses: {
        USERNAME: cognitoUser.username,
        NEW_PASSWORD: newPassword,
        ...Object.fromEntries(
          Object.entries(attributes || {}).map(([k, v]) => [`userAttributes.${k}`, v as string])
        ),
      },
    });
    const result = await cognitoClient.send(cmd);
    storeTokens(result);
    const parsed = parseIdToken(result.AuthenticationResult!.IdToken!);
    setUser(parsed);

    try {
      await apiClient.setRefreshToken(
        result.AuthenticationResult!.RefreshToken!,
        result.AuthenticationResult!.IdToken!
      );
    } catch (e) { console.warn('Failed to persist refresh cookie:', e); }

    navigate('/app');
  }, [config.clientId, cognitoClient, storeTokens, parseIdToken, navigate]);

  const signOut = useCallback(async () => {
    try {
      const accessToken = _inMemoryIdToken; // Use in-memory token for global sign-out
      if (accessToken) {
        await cognitoClient.send(new GlobalSignOutCommand({ AccessToken: accessToken }));
      }
    } catch (e) { /* ignore */ }
    _inMemoryIdToken = null;
    setAuthToken(null);
    try { await apiClient.logout(); } catch (e) { /* ignore */ }
    setUser(null);
    navigate('/login');
  }, [cognitoClient, navigate]);

  const value = useMemo(() => ({
    user, isAuthenticated: !!user, isLoading, signIn, completePasswordChange, signOut,
  }), [user, isLoading, signIn, completePasswordChange, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
