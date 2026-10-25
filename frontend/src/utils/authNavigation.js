// Returning to the login screen explicitly ends the account session.
// Leaving a notebook for the home screen does not log the account out.
export async function logoutBeforeNavigation(to, from, logout, storage) {
  if (to.path !== '/' || from.path === '/' || !from.matched.length) return false
  await logout()
  for (const key of ['userId', 'realName', 'coacherName', 'level', 'byadmin', 'password']) {
    storage.removeItem(key)
  }
  storage.setItem('home2login', 'true')
  return true
}
