import { createRouter, createWebHistory } from 'vue-router'
import LibraryView from '../views/LibraryView.vue'
import GenerateView from '../views/GenerateView.vue'
import ReaderView from '../views/ReaderView.vue'

const routes = [
  {
    path: '/',
    name: 'Library',
    component: LibraryView,
  },
  {
    path: '/generate',
    name: 'Generate',
    component: GenerateView,
  },
  {
    path: '/read/:comicId',
    name: 'Reader',
    component: ReaderView,
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
