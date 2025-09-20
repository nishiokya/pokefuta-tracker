import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';
import sampleManholes from '@/data/sample-manholes.json';

export async function GET(request: NextRequest) {
  try {
    // Check if Supabase is configured
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (!supabaseUrl || !supabaseKey || supabaseUrl.includes('dummy')) {
      // Return sample data if Supabase is not configured
      console.log('Using sample manhole data');
      const { searchParams } = new URL(request.url);
      const visited = searchParams.get('visited');

      let filteredManholes = sampleManholes;

      // Apply visited filter
      if (visited === 'true') {
        filteredManholes = sampleManholes.filter(m => m.is_visited);
      } else if (visited === 'false') {
        filteredManholes = sampleManholes.filter(m => !m.is_visited);
      }

      return NextResponse.json(filteredManholes);
    }

    const supabase = createRouteHandlerClient<Database>({ cookies });
    const { searchParams } = new URL(request.url);

    // Get query parameters
    const lat = searchParams.get('lat');
    const lng = searchParams.get('lng');
    const radius = searchParams.get('radius') || '50'; // km
    const limit = parseInt(searchParams.get('limit') || '100');
    const visited = searchParams.get('visited'); // 'true', 'false', or null for all

    let query = supabase
      .from('manhole')
      .select(`
        *,
        visit!left (
          id,
          visited_at,
          photo_count
        )
      `)
      .limit(limit);

    // Add geographic filtering if coordinates provided
    if (lat && lng) {
      // For now, we'll use a simple bounding box filter
      // In production, you would use PostGIS functions
      const latFloat = parseFloat(lat);
      const lngFloat = parseFloat(lng);
      const radiusKm = parseFloat(radius);
      const latDelta = radiusKm / 111; // Approximate km per degree of latitude
      const lngDelta = radiusKm / (111 * Math.cos(latFloat * Math.PI / 180));

      query = query
        .gte('latitude', latFloat - latDelta)
        .lte('latitude', latFloat + latDelta)
        .gte('longitude', lngFloat - lngDelta)
        .lte('longitude', lngFloat + lngDelta);
    }

    // Add visited filter
    if (visited === 'true') {
      query = query.not('visit', 'is', null);
    } else if (visited === 'false') {
      query = query.is('visit', null);
    }

    const { data: manholes, error } = await query;

    if (error) {
      console.error('Error fetching manholes:', error);
      return NextResponse.json(
        { error: 'Failed to fetch manholes' },
        { status: 500 }
      );
    }

    // Transform data to include visit status
    const manholesWithVisitStatus = manholes?.map(manhole => ({
      ...manhole,
      is_visited: manhole.visit && manhole.visit.length > 0,
      last_visit: manhole.visit?.[0]?.visited_at || null,
      photo_count: manhole.visit?.[0]?.photo_count || 0
    })) || [];

    return NextResponse.json(manholesWithVisitStatus);

  } catch (error) {
    console.error('API Error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });
    const body = await request.json();

    // Validate required fields
    const {
      name,
      description,
      prefecture,
      city,
      address,
      latitude,
      longitude,
      source_url
    } = body;

    if (!name || !latitude || !longitude) {
      return NextResponse.json(
        { error: 'Name, latitude, and longitude are required' },
        { status: 400 }
      );
    }

    // Insert new manhole
    const { data: manhole, error } = await supabase
      .from('manhole')
      .insert({
        name,
        description,
        prefecture,
        city,
        address,
        latitude: parseFloat(latitude),
        longitude: parseFloat(longitude),
        source_url,
        created_at: new Date().toISOString()
      })
      .select()
      .single();

    if (error) {
      console.error('Error creating manhole:', error);
      return NextResponse.json(
        { error: 'Failed to create manhole' },
        { status: 500 }
      );
    }

    return NextResponse.json(manhole, { status: 201 });

  } catch (error) {
    console.error('API Error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}