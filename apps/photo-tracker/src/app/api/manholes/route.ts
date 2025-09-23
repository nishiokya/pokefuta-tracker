import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';
import sampleManholes from '@/data/sample-manholes.json';

// Helper functions to extract coordinates from PostGIS format
function extractLatFromLocation(location: string): number | undefined {
  if (!location) return undefined;
  const match = location.match(/POINT\(([^\s]+)\s+([^\s]+)\)/);
  return match ? parseFloat(match[2]) : undefined;
}

function extractLngFromLocation(location: string): number | undefined {
  if (!location) return undefined;
  const match = location.match(/POINT\(([^\s]+)\s+([^\s]+)\)/);
  return match ? parseFloat(match[1]) : undefined;
}

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
    const limit = parseInt(searchParams.get('limit') || '1000');
    const visited = searchParams.get('visited'); // 'true', 'false', or null for all

    try {
      // Try to fetch from manhole table
      const { data: manholes, error } = await supabase
        .from('manhole')
        .select('*')
        .limit(limit);

      if (error) {
        console.error('Database error:', error);
        // If there's a database error, fall back to sample data
        throw new Error(`Database query failed: ${error.message}`);
      }

      // If we have data, transform it to our expected format
      if (manholes && manholes.length > 0) {
        const manholesWithVisitStatus = manholes.map(manhole => ({
          ...manhole,
          name: manhole.title || manhole.name || 'ポケふた',
          description: manhole.description || '',
          city: manhole.municipality || manhole.city || '',
          address: manhole.address || '',
          // Extract coordinates from PostGIS location if needed
          latitude: manhole.latitude || extractLatFromLocation(manhole.location),
          longitude: manhole.longitude || extractLngFromLocation(manhole.location),
          is_visited: false, // Default to false since we don't have visit data yet
          last_visit: null,
          photo_count: 0
        }));

        // Apply visited filter to database results
        let filteredManholes = manholesWithVisitStatus;
        if (visited === 'true') {
          filteredManholes = manholesWithVisitStatus.filter(m => m.is_visited);
        } else if (visited === 'false') {
          filteredManholes = manholesWithVisitStatus.filter(m => !m.is_visited);
        }

        return NextResponse.json(filteredManholes);
      }

      // If table is empty, fall back to sample data
      console.log('Manhole table is empty, using sample data');
      throw new Error('Table is empty');

    } catch (dbError) {
      console.log('Database error, falling back to sample data:', (dbError as Error).message);
      // Fall back to sample data as before
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