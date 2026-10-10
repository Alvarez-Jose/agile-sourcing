export interface UserProfile {
  uid: string;
  email: string;
  name?: string | null;
  photoURL?: string | null;
  department?: string | null;
  clearance?: string;
  is_approved: boolean;
  role?: string;
  created_at?: string | null;
}

export interface StoredAuthData {
  idToken?: string;
  userProfile?: UserProfile;
}
