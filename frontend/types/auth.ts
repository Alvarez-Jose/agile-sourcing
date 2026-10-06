export interface UserProfile {
  uid: string;
  email: string;
  name?: string;
  photoURL?: string;
  is_approved: boolean;
  role?: string;
  created_at?: string;
}

export interface StoredAuthData {
  idToken?: string;
  userProfile?: UserProfile;
}
