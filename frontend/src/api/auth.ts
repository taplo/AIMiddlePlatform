import client from './client'

export async function login(username: string, password: string) {
  const res = await client.post('/api/v1/auth/login', { username, password })
  return res.data
}
