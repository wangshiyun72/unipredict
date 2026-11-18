import { reactive } from 'vue'

function load() {
  try {
    return JSON.parse(localStorage.getItem('unipredict_auth') || '{}')
  } catch (e) {
    return {}
  }
}

const saved = load()

export const auth = reactive({
  token: saved.token || '',
  user: saved.user || null,
  get isAdmin() {
    return this.user && this.user.role === 'admin'
  },
  set(token, user) {
    this.token = token
    this.user = user
    try {
      localStorage.setItem('unipredict_auth', JSON.stringify({ token, user }))
    } catch (e) { /* 浏览器禁用存储时忽略 */ }
  },
  clear() {
    this.token = ''
    this.user = null
    try { localStorage.removeItem('unipredict_auth') } catch (e) { /* ignore */ }
  }
})
