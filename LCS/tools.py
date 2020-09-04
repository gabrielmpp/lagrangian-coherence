import numpy as np
from skimage.feature import hessian_matrix_eigvals
from scipy.ndimage import gaussian_filter
import xarray as xr
import pandas as pd


def find_ridges_spherical_hessian(da, sigma=.5, scheme='first_order',
                                  angle=5):
    """
    Method to in apply a Hessian filter in spherical coordinates
    Parameters
    ----------
    sigma - float, smoothing intensity
    da - xarray.dataarray
    scheme - str, 'first_order' for x[i+1] - x[i] and second order for x[i+1] - x[i-1]
    angle - float in degrees to relax height perpendicularity requirement
    Returns
    -------
    Filtered array

    """
    da = da.copy()
    # Gaussian filter
    if isinstance(sigma, (float, int)):
        da = da.copy(data=gaussian_filter(da, sigma=sigma))

    # Initializing
    earth_r = 6371000
    x = da.longitude.copy() * np.pi / 180
    y = da.latitude.copy() * np.pi / 180
    dx = x.diff('longitude') * earth_r * np.cos(y)
    dy = y.diff('latitude') * earth_r
    dx_scaling = 2 * da.longitude.diff('longitude').values[0]  # grid spacing for xr.differentiate
    dy_scaling = 2 * da.latitude.diff('latitude').values[0]  # grid spacing
    print(1)
    # Calc derivatives
    if scheme == 'second_order':
        ddadx = dx_scaling * da.differentiate('longitude') / dx
        ddady = dy_scaling * da.differentiate('latitude') / dy
        d2dadx2 = dx_scaling * ddadx.differentiate('longitude') / dx
        d2dadxdy = dy_scaling * ddadx.differentiate('latitude') / dy
        d2dady2 = dx_scaling * ddady.differentiate('latitude') / dy
        d2dadydx = d2dadxdy.copy()
    elif scheme == 'first_order':
        ddadx = da.diff('longitude') / dx
        ddady = da.diff('latitude') / dy
        d2dadx2 = ddadx.diff('longitude') / dx
        d2dadxdy = ddadx.diff('latitude') / dy
        d2dady2 = ddady.diff('latitude') / dy
        d2dadydx = d2dadxdy.copy()
    # Assembling Hessian array
    print(2)
    gradient = xr.concat([ddadx, ddady],
                         dim=pd.Index(['ddadx', 'ddady'],
                                      name='elements'))
    hessian = xr.concat([d2dadx2, d2dadxdy, d2dadydx, d2dady2],
                        dim=pd.Index(['d2dadx2', 'd2dadxdy', 'd2dadydx', 'd2dady2'],
                                     name='elements'))
    hessian = hessian.stack({'points': ['latitude', 'longitude']})
    gradient = gradient.stack({'points': ['latitude', 'longitude']})
    hessian = hessian.where(np.abs(hessian) != np.inf, np.nan)
    hessian = hessian.dropna('points', how='any')
    gradient = gradient.sel(points=hessian.points)
    grad_vals = gradient.transpose(..., 'points').values
    hess_vals = hessian.transpose(..., 'points').values

    hess_vals = hess_vals.reshape([2, 2, hessian.shape[-1]])
    val_list = []
    eigmin_list = []
    print('Computing hessian eigvectors')
    for i in range(hess_vals.shape[-1]):
        print(str(100 * i / hess_vals.shape[-1]) + ' %')
        eig = np.linalg.eig(hess_vals[:, :, i])
        eigvector = eig[1][np.argmax(eig[0])]  # eigenvetor of smallest eigenvalue
        # eigvector = eigvector/np.max(np.abs(eigvector))  # normalizing the eigenvector to recover t hat

        dt_angle = np.arccos(np.dot(np.flip(eigvector), grad_vals[:, i]) / (np.linalg.norm(eigvector) *
                                                                            np.linalg.norm(grad_vals[:, i])))
        val_list.append(dt_angle)
        eigmin_list.append(np.sign(np.min(eig[0])))

    dt_prod = hessian.isel(elements=0).drop('elements').copy(data=val_list).unstack()
    dt_prod_ = dt_prod.copy()
    eigmin = hessian.isel(elements=0).drop('elements').copy(data=eigmin_list).unstack()

    dt_prod = dt_prod.where(np.abs(dt_prod_) <= angle * np.pi / 180, 0)
    dt_prod = dt_prod.where(np.abs(dt_prod_) > angle * np.pi / 180, 1)
    dt_prod = dt_prod.where(eigmin == -1, 0)

    return dt_prod, eigmin


def latlonsel(array, lat, lon, latname='lat', lonname='lon'):
    """
    Function to crop array based on lat and lon intervals given by slice or list.
    This function is able to crop across cyclic boundaries.

    :param array: xarray.Datarray
    :param lat: list or slice (min, max)
    :param lon: list or slice(min, max)
    :return: cropped array
    """
    assert latname in array.coords, f"Coord. {latname} not present in array"
    assert lonname in array.coords, f"Coord. {lonname} not present in array"

    if isinstance(lat, slice):
        lat1 = lat.start
        lat2 = lat.stop
    elif isinstance(lat, list):
        lat1 = lat[0]
        lat2 = lat[-1]
    if isinstance(lon, slice):
        lon1 = lon.start
        lon2 = lon.stop
    elif isinstance(lon, list):
        lon1 = lon[0]
        lon2 = lon[-1]

    lonmask = (array[lonname] < lon2) & (array[lonname] > lon1)
    latmask = (array[latname] < lat2) & (array[latname] > lat1)
    array = array.where(lonmask, drop=True).where(latmask, drop=True)
    return array
