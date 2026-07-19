import client from "./client"

export interface LoginResponse {
  access_token: string
  refresh_token: string
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>("/auth/login", { username, password })
  return data
}

export async function refresh(refreshToken: string): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>("/auth/refresh", { refresh_token: refreshToken })
  return data
}
