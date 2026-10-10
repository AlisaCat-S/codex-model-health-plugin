export interface AccountDisplayInput {
  name: string
  email?: string | null
}

export function accountDisplayName(account: AccountDisplayInput): string {
  const email = account.email?.trim()
  if (email) return email
  return account.name.trim()
}
