import axios from 'axios'
import { ElMessage } from 'element-plus'
import { auth } from '../store'
import router from '../router'

const http = axios.create({ baseURL: '/api/v1', timeout: 300000 })

http.interceptors.request.use((config) => {
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

function detailText(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI 参数校验错误
    return detail.map((d) => String(d.msg || '').replace(/^Value error, /, '')).join('；')
  }
  return JSON.stringify(detail)
}

http.interceptors.response.use(
  (res) => res.data,
  async (err) => {
    const status = err.response?.status
    let detail = err.response?.data?.detail
    // 下载文件时错误信息在 Blob 里
    if (err.response?.data instanceof Blob) {
      try { detail = JSON.parse(await err.response.data.text()).detail } catch (e) { /* ignore */ }
    }
    const msg = detailText(detail) || err.message
    if (status === 401) {
      auth.clear()
      if (router.currentRoute.value.name !== 'login') {
        ElMessage.warning('登录已过期，请重新登录')
        router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
      }
    } else if (!err.config?.silent) {
      const prefix = status === 429 ? '请求被限流：' : status === 503 ? '服务繁忙：' : ''
      ElMessage.error({ message: prefix + msg, duration: 5000 })
    }
    const e = new Error(msg)
    e.status = status
    return Promise.reject(e)
  }
)

export async function download(url, filename, method = 'get', data = null) {
  const blob = await http.request({ url, method, data, responseType: 'blob' })
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}

export default http
