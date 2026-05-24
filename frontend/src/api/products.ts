import apiClient from './client';
import type { ProductInfo } from '../types';

export async function fetchProducts(type?: string): Promise<ProductInfo[]> {
  const { data } = await apiClient.get<{ products: ProductInfo[] }>('/products', {
    params: type ? { type } : {},
  });
  return data.products;
}

export async function fetchProductDetail(id: number): Promise<unknown> {
  const { data } = await apiClient.get(`/products/${id}`);
  return data;
}
